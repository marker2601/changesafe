import importlib.util
import json
import os
import subprocess
import sys
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from types import ModuleType
from typing import Any

import httpx
import pytest
import yaml

from changesafe.config import Mode, Settings
from changesafe.context.base import DecisionWriteback
from changesafe.context.replay import ReplayDataHubContext
from changesafe.demo import DEMO_TARGET_URN
from changesafe.domain import (
    ChangeRequest,
    ContextMode,
    DataHubReceipt,
    SchemaCatalog,
    WarehouseCheck,
    WarehouseValidationMode,
    WarehouseValidationResult,
    WarehouseValidationStatus,
)

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "smoke_competition.py"
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
SAFE_TOP_LEVEL_KEYS = {"status", "results"}
SAFE_OPERATION_KEYS = {
    "field",
    "operation",
    "context_mode",
    "upstream_count",
    "downstream_count",
    "deterministic_score",
    "warehouse_status",
    "warehouse_rows_evaluated",
    "warehouse_populated_row_count",
    "warehouse_unsafe_row_count",
    "receipt_mode",
}


def load_ci_workflow() -> dict[str, Any]:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def workflow_step(job: dict[str, Any], name: str) -> dict[str, Any]:
    steps = {step.get("name"): step for step in job["steps"]}
    assert name in steps
    return steps[name]


def load_smoke_module() -> ModuleType:
    if not SCRIPT.is_file():
        pytest.fail("competition smoke script is not implemented")
    spec = importlib.util.spec_from_file_location("smoke_competition", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LiveRecordedDataHub:
    def __init__(self) -> None:
        self.delegate = ReplayDataHubContext.from_default()
        self.writeback_calls: list[DecisionWriteback] = []
        self.closed = False

    async def load(self, change: ChangeRequest):
        context = await self.delegate.load(change)
        return context.model_copy(
            update={
                "provenance": context.provenance.model_copy(
                    update={"mode": ContextMode.LIVE, "snapshot_hash": None}
                )
            }
        )

    async def discover_schema(self, asset_urn: str) -> SchemaCatalog:
        context = await self.load(
            ChangeRequest(
                asset_urn=asset_urn,
                operation="rename",
                field="cust_email",
                new_field="primary_email",
                source_commit="smoke-schema-discovery",
                requested_by="smoke-test",
            )
        )
        return SchemaCatalog(
            target_urn=context.target_urn,
            target_name=context.target_name,
            schema_fields=context.schema_fields,
            provenance=context.provenance,
        )

    async def writeback(
        self,
        decision: DecisionWriteback,
        **_kwargs: object,
    ) -> DataHubReceipt:
        self.writeback_calls.append(decision)
        raise AssertionError("competition smoke attempted DataHub writeback")

    async def close(self) -> None:
        self.closed = True


class PassingWarehousePort:
    def __init__(self, relation: str) -> None:
        self.relation = relation
        self.calls: list[ChangeRequest] = []
        self.closed = False

    async def validate(self, change: ChangeRequest, _context: object):
        self.calls.append(change)
        completed_at = datetime.now(UTC)
        return WarehouseValidationResult(
            status=WarehouseValidationStatus.PASSED,
            mode=WarehouseValidationMode.AGGREGATE,
            environment_label="competition-non-production",
            operation=change.operation,
            field=change.field,
            aggregate_query_started=True,
            relation_fingerprint=sha256(self.relation.encode()).hexdigest(),
            started_at=completed_at,
            completed_at=completed_at,
            rows_evaluated=12,
            populated_row_count=10,
            unsafe_row_count=(0 if change.operation.value == "type_change" else None),
            checks=[
                WarehouseCheck(
                    code="aggregate_validation",
                    label="Aggregate validation",
                    passed=True,
                    detail="Aggregate checks passed.",
                )
            ],
        )

    async def close(self) -> None:
        self.closed = True


class ForbiddenWarehousePort:
    async def validate(self, *_args: object, **_kwargs: object):
        raise AssertionError("datahub-only smoke reached the warehouse")

    async def close(self) -> None:
        raise AssertionError("datahub-only smoke constructed a warehouse port")


class CapturingHttpPort:
    def __init__(self) -> None:
        self.settings: Settings | None = None
        self.calls = 0

    @asynccontextmanager
    async def __call__(self, app: Any):
        self.calls += 1
        self.settings = app.state.settings
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://smoke.invalid",
        ) as client:
            yield client


def live_settings(tmp_path: Path, *, warehouse: bool) -> Settings:
    relation = "SAFE_DB.SAFE_SCHEMA.ORDER_DETAILS"
    values: dict[str, object] = {
        "_env_file": None,
        "mode": Mode.LIVE,
        "changesafe_data_path": tmp_path / "unused.db",
        "datahub_gms_url": "https://metadata.invalid",
        "datahub_gms_token": "private-datahub-token",
        "github_token": "private-github-token",
        "changesafe_github_repository": "private/repository",
        "public_pr_enabled": True,
        "public_writeback_enabled": True,
        "save_document_restrict_updates": False,
        "changesafe_admin_token": "private-admin-token",
    }
    if warehouse:
        values.update(
            {
                "warehouse_validation_enabled": True,
                "snowflake_account": "private-account",
                "snowflake_user": "private-user",
                "snowflake_authenticator": "SNOWFLAKE_JWT",
                "snowflake_private_key_path": tmp_path / "private-key.p8",
                "snowflake_warehouse": "COMPUTE_WH",
                "snowflake_database": "SAFE_DB",
                "snowflake_schema": "SAFE_SCHEMA",
                "snowflake_role": "CHANGESAFE_READONLY",
                "snowflake_target_relation_allowlist": {
                    DEMO_TARGET_URN: relation
                },
            }
        )
    return Settings(**values)


@pytest.mark.asyncio
async def test_datahub_only_never_imports_or_calls_snowflake(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    smoke = load_smoke_module()
    context = LiveRecordedDataHub()
    http_port = CapturingHttpPort()
    imported: list[str] = []

    def forbid_connector(name: str) -> None:
        imported.append(name)
        raise AssertionError("Snowflake connector import is forbidden")

    monkeypatch.setattr(
        "changesafe.warehouse.factory.import_module", forbid_connector
    )
    summary = await smoke.run_competition_smoke(
        live_settings(tmp_path, warehouse=True),
        smoke.SmokeOptions(datahub_only=True),
        context_port=context,
        warehouse_port=ForbiddenWarehousePort(),
        http_port=http_port,
    )

    assert summary["status"] == "passed"
    assert imported == []
    assert context.writeback_calls == []
    assert http_port.settings is not None
    assert http_port.settings.warehouse_validation_enabled is False
    assert http_port.settings.warehouse_validation_required is False


@pytest.mark.asyncio
async def test_default_smoke_forces_external_mutations_off_and_approves_preview(
    tmp_path: Path,
) -> None:
    smoke = load_smoke_module()
    context = LiveRecordedDataHub()
    relation = "SAFE_DB.SAFE_SCHEMA.ORDER_DETAILS"
    warehouse = PassingWarehousePort(relation)
    http_port = CapturingHttpPort()

    summary = await smoke.run_competition_smoke(
        live_settings(tmp_path, warehouse=True),
        smoke.SmokeOptions(),
        context_port=context,
        warehouse_port=warehouse,
        http_port=http_port,
    )

    assert summary["status"] == "passed"
    assert context.writeback_calls == []
    assert [call.operation.value for call in warehouse.calls] == [
        "rename",
        "remove",
        "type_change",
    ]
    assert warehouse.closed is True
    assert context.closed is True
    assert http_port.settings is not None
    assert http_port.settings.public_pr_enabled is False
    assert http_port.settings.public_writeback_enabled is False
    assert {item["receipt_mode"] for item in summary["results"]} == {
        "preview"
    }


@pytest.mark.parametrize(
    "partial_environment",
    [
        {},
        {
            "SNOWFLAKE_ACCOUNT": "private-account",
            "SNOWFLAKE_USER": "private-user",
        },
    ],
)
def test_required_warehouse_with_incomplete_configuration_exits_safely(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    partial_environment: dict[str, str],
) -> None:
    smoke = load_smoke_module()
    for name in (
        "SNOWFLAKE_ACCOUNT",
        "SNOWFLAKE_USER",
        "SNOWFLAKE_AUTHENTICATOR",
        "SNOWFLAKE_PRIVATE_KEY_PATH",
        "SNOWFLAKE_WAREHOUSE",
        "SNOWFLAKE_DATABASE",
        "SNOWFLAKE_SCHEMA",
        "SNOWFLAKE_ROLE",
        "SNOWFLAKE_TARGET_RELATION_ALLOWLIST",
    ):
        monkeypatch.delenv(name, raising=False)
    for name, value in partial_environment.items():
        monkeypatch.setenv(name, value)

    status = smoke.main(
        ["--require-warehouse"],
        env_file=None,
    )
    output = json.loads(capsys.readouterr().out)

    assert status != 0
    assert output == {"status": "warehouse_configuration_incomplete"}
    assert "private-account" not in json.dumps(output)
    assert "private-user" not in json.dumps(output)


def test_required_warehouse_rejects_a_missing_private_key_before_connector_use(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    smoke = load_smoke_module()
    environment = {
        "SNOWFLAKE_ACCOUNT": "private-account",
        "SNOWFLAKE_USER": "private-user",
        "SNOWFLAKE_AUTHENTICATOR": "SNOWFLAKE_JWT",
        "SNOWFLAKE_PRIVATE_KEY_PATH": str(tmp_path / "missing-private-key.p8"),
        "SNOWFLAKE_WAREHOUSE": "COMPUTE_WH",
        "SNOWFLAKE_DATABASE": "SAFE_DB",
        "SNOWFLAKE_SCHEMA": "SAFE_SCHEMA",
        "SNOWFLAKE_ROLE": "CHANGESAFE_READONLY",
        "SNOWFLAKE_TARGET_RELATION_ALLOWLIST": json.dumps(
            {DEMO_TARGET_URN: "SAFE_DB.SAFE_SCHEMA.ORDER_DETAILS"}
        ),
    }
    for name, value in environment.items():
        monkeypatch.setenv(name, value)

    with pytest.raises(smoke.SmokeFailure) as captured:
        smoke._load_settings(
            smoke.SmokeOptions(require_warehouse=True),
            env_file=None,
        )

    assert captured.value.status == "warehouse_configuration_incomplete"


def test_cli_emits_one_safe_json_document_without_dependency_warnings() -> None:
    command = """
import json
import runpy
import sys

runpy.run_path(sys.argv[1], run_name="smoke_competition_import")
import datahub_agent_context.mcp_tools.save_document  # noqa: F401, E402
print(json.dumps({"status": "passed"}))
"""

    completed = subprocess.run(
        [sys.executable, "-c", command, str(SCRIPT)],
        cwd=ROOT,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        check=False,
    )
    output = json.loads(completed.stdout)

    assert completed.returncode == 0
    assert completed.stderr == ""
    assert output == {"status": "passed"}


def test_ci_sets_live_mode_only_on_the_credentialed_smoke_step() -> None:
    workflow = load_ci_workflow()
    readiness = workflow["jobs"]["optional-live-readiness"]
    smoke = workflow_step(readiness, "Competition live and warehouse smoke")

    assert "CHANGESAFE_MODE" not in readiness.get("env", {})
    assert "CHANGESAFE_MODE" not in workflow["jobs"]["quality"].get("env", {})
    assert smoke["env"]["CHANGESAFE_MODE"] == "live"


def test_ci_materializes_ephemeral_key_before_smoke_and_always_cleans_it() -> None:
    workflow = load_ci_workflow()
    readiness = workflow["jobs"]["optional-live-readiness"]
    names = [step.get("name") for step in readiness["steps"]]
    materialize_name = "Materialize ephemeral Snowflake private key"
    smoke_name = "Competition live and warehouse smoke"
    cleanup_name = "Remove ephemeral Snowflake private key"

    assert names.index(materialize_name) < names.index(smoke_name)
    assert names.index(smoke_name) < names.index(cleanup_name)
    materialize = workflow_step(readiness, materialize_name)
    cleanup = workflow_step(readiness, cleanup_name)
    materialize_run = materialize["run"]
    cleanup_run = cleanup["run"]

    assert materialize["env"] == {
        "SNOWFLAKE_PRIVATE_KEY_BASE64": (
            "${{ secrets.SNOWFLAKE_PRIVATE_KEY_BASE64 }}"
        )
    }
    assert "umask 077" in materialize_run
    assert "base64 --decode" in materialize_run
    assert 'chmod 600 "${key_path}"' in materialize_run
    assert 'SNOWFLAKE_PRIVATE_KEY_PATH=%s\\n' in materialize_run
    assert '>> "${GITHUB_ENV}"' in materialize_run
    assert "set -x" not in materialize_run
    assert not any(
        "echo" in line and "SNOWFLAKE_PRIVATE_KEY_BASE64" in line
        for line in materialize_run.splitlines()
    )
    assert cleanup["if"] == "always()"
    assert 'rm -f -- "${key_path}"' in cleanup_run


def test_ci_credential_completeness_and_safe_skip_cover_every_input() -> None:
    workflow = load_ci_workflow()
    readiness = workflow["jobs"]["optional-live-readiness"]
    job_env = readiness["env"]
    materialize = workflow_step(
        readiness, "Materialize ephemeral Snowflake private key"
    )
    smoke = workflow_step(readiness, "Competition live and warehouse smoke")
    skipped = workflow_step(readiness, "Explain skipped warehouse smoke")
    required = {
        "DATAHUB_GMS_URL",
        "DATAHUB_GMS_TOKEN",
        "SNOWFLAKE_ACCOUNT",
        "SNOWFLAKE_USER",
        "SNOWFLAKE_AUTHENTICATOR",
        "SNOWFLAKE_WAREHOUSE",
        "SNOWFLAKE_DATABASE",
        "SNOWFLAKE_SCHEMA",
        "SNOWFLAKE_ROLE",
        "SNOWFLAKE_TARGET_RELATION_ALLOWLIST",
        "SNOWFLAKE_PRIVATE_KEY_BASE64_PRESENT",
    }

    assert "SNOWFLAKE_PRIVATE_KEY_PATH" not in job_env
    assert "SNOWFLAKE_PRIVATE_KEY_BASE64" not in job_env
    assert job_env["SNOWFLAKE_PRIVATE_KEY_BASE64_PRESENT"] == (
        "${{ secrets.SNOWFLAKE_PRIVATE_KEY_BASE64 != '' }}"
    )
    for name in required:
        assert name in materialize["if"]
        assert name in smoke["if"]
        assert name in skipped["if"]


@pytest.mark.asyncio
async def test_json_summary_is_restricted_to_safe_counts_and_identifiers(
    tmp_path: Path,
) -> None:
    smoke = load_smoke_module()
    context = LiveRecordedDataHub()
    relation = "SAFE_DB.SAFE_SCHEMA.ORDER_DETAILS"
    warehouse = PassingWarehousePort(relation)

    summary = await smoke.run_competition_smoke(
        live_settings(tmp_path, warehouse=True),
        smoke.SmokeOptions(require_live_datahub=True, require_warehouse=True),
        context_port=context,
        warehouse_port=warehouse,
        http_port=CapturingHttpPort(),
    )
    serialized = json.dumps(summary, sort_keys=True)

    assert set(summary) == SAFE_TOP_LEVEL_KEYS
    assert len(summary["results"]) == 3
    assert all(set(item) == SAFE_OPERATION_KEYS for item in summary["results"])
    assert all(item["context_mode"] == "live" for item in summary["results"])
    for forbidden in (
        "private-datahub-token",
        "private-github-token",
        "private-admin-token",
        "private-account",
        "private-user",
        relation,
        "https://metadata.invalid",
        "fingerprint",
        "query",
        "sql",
        "path",
        "role",
        "token",
    ):
        assert forbidden.casefold() not in serialized.casefold()
