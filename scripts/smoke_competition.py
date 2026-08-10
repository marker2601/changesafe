"""Run the competition workflow without enabling any external mutation."""

from __future__ import annotations

import argparse
import asyncio
import json
import tempfile
import warnings
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Protocol

import httpx
from fastapi import FastAPI
from pydantic import ValidationError

from changesafe.api import create_app
from changesafe.config import Mode, Settings
from changesafe.context.base import DataHubContextPort
from changesafe.demo import DEMO_TARGET_URN
from changesafe.domain import ChangeOperation, ContextMode, SchemaCatalog
from changesafe.warehouse.base import WarehouseValidationPort

warnings.filterwarnings(
    "ignore",
    message=r"The new datahub SDK .*",
    module=r"datahub_agent_context\.mcp_tools\.save_document",
)

EXPECTED_SCHEMA_FIELD_COUNT = 55
EXPECTED_ARTIFACT_COUNT = 7
EXPECTED_STATIC_CHECK_COUNT = 12
TERMINAL_RUN_STATES = {
    "awaiting_approval",
    "context_fallback_required",
    "failed",
    "publication_failed",
}


class SmokeFailure(RuntimeError):
    """A stable, credential-safe smoke failure."""

    def __init__(self, status: str) -> None:
        super().__init__(status)
        self.status = status


class SmokeOptions:
    def __init__(
        self,
        *,
        datahub_only: bool = False,
        require_live_datahub: bool = False,
        require_warehouse: bool = False,
    ) -> None:
        self.datahub_only = datahub_only
        self.require_live_datahub = require_live_datahub
        self.require_warehouse = require_warehouse


class HttpPort(Protocol):
    def __call__(self, app: FastAPI) -> Any: ...


@asynccontextmanager
async def _default_http_port(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://competition-smoke.invalid",
    ) as client:
        yield client


def _effective_settings(
    settings: Settings,
    options: SmokeOptions,
    *,
    database_path: Path,
) -> Settings:
    values = settings.model_dump()
    values.update(
        {
            "changesafe_data_path": database_path,
            "public_pr_enabled": False,
            "public_writeback_enabled": False,
            "live_evidence_required": options.require_live_datahub,
        }
    )
    if options.datahub_only:
        values.update(
            {
                "warehouse_validation_enabled": False,
                "warehouse_validation_required": False,
            }
        )
    elif options.require_warehouse:
        values.update(
            {
                "warehouse_validation_enabled": True,
                "warehouse_validation_required": True,
            }
        )
    return Settings(_env_file=None, **values)


def _select_requests(catalog: SchemaCatalog) -> list[dict[str, object]]:
    fields = {field.name: field for field in catalog.schema_fields}
    selected = {"cust_email", "order_total", "order_date"}
    if not selected.issubset(fields):
        raise SmokeFailure("catalog_contract_failed")
    existing = {name.casefold() for name in fields}
    if "primary_email" in existing:
        raise SmokeFailure("catalog_contract_failed")
    return [
        {
            "asset_urn": DEMO_TARGET_URN,
            "operation": ChangeOperation.RENAME.value,
            "field": "cust_email",
            "new_field": "primary_email",
            "source_commit": "showcase-ecommerce-safe-rename",
            "requested_by": "competition-smoke",
        },
        {
            "asset_urn": DEMO_TARGET_URN,
            "operation": ChangeOperation.REMOVE.value,
            "field": "order_total",
            "source_commit": "showcase-ecommerce-safe-remove",
            "requested_by": "competition-smoke",
        },
        {
            "asset_urn": DEMO_TARGET_URN,
            "operation": ChangeOperation.TYPE_CHANGE.value,
            "field": "order_date",
            "old_type": fields["order_date"].data_type,
            "new_type": "VARCHAR(320)",
            "source_commit": "showcase-ecommerce-safe-type-change",
            "requested_by": "competition-smoke",
        },
    ]


async def _wait_for_run(
    client: httpx.AsyncClient, run_id: str
) -> dict[str, Any]:
    for _ in range(600):
        response = await client.get(f"/api/runs/{run_id}")
        if response.status_code != 200:
            raise SmokeFailure("api_contract_failed")
        payload = response.json()
        if payload.get("state") in TERMINAL_RUN_STATES:
            return payload
        await asyncio.sleep(0.1)
    raise SmokeFailure("analysis_timed_out")


def _validate_catalog(payload: dict[str, Any]) -> SchemaCatalog:
    try:
        catalog = SchemaCatalog.model_validate(payload)
    except ValidationError as exc:
        raise SmokeFailure("catalog_contract_failed") from exc
    names = [field.name.casefold() for field in catalog.schema_fields]
    concrete = all(field.data_type.strip() for field in catalog.schema_fields)
    if (
        len(catalog.schema_fields) != EXPECTED_SCHEMA_FIELD_COUNT
        or len(set(names)) != EXPECTED_SCHEMA_FIELD_COUNT
        or not concrete
    ):
        raise SmokeFailure("catalog_contract_failed")
    return catalog


def _safe_operation_summary(
    run: dict[str, Any], receipt: dict[str, Any]
) -> dict[str, object]:
    analysis = run.get("analysis")
    request = run.get("request")
    if not isinstance(analysis, dict) or not isinstance(request, dict):
        raise SmokeFailure("api_contract_failed")
    context = analysis.get("context")
    risk = analysis.get("risk")
    artifacts = analysis.get("artifacts")
    validation = analysis.get("validation")
    warehouse = analysis.get("warehouse_validation")
    if not all(
        isinstance(item, dict)
        for item in (context, risk, artifacts, validation, warehouse)
    ):
        raise SmokeFailure("api_contract_failed")

    files = artifacts.get("files")
    checks = validation.get("checks")
    upstream = context.get("upstream_assets")
    downstream = context.get("downstream_assets")
    provenance = context.get("provenance")
    if (
        not isinstance(files, dict)
        or not isinstance(checks, list)
        or not isinstance(upstream, list)
        or not isinstance(downstream, list)
        or not isinstance(provenance, dict)
    ):
        raise SmokeFailure("api_contract_failed")
    passed_checks = sum(
        item.get("passed") is True for item in checks if isinstance(item, dict)
    )
    if (
        len(files) != EXPECTED_ARTIFACT_COUNT
        or len(checks) != EXPECTED_STATIC_CHECK_COUNT
        or passed_checks != EXPECTED_STATIC_CHECK_COUNT
        or validation.get("passed") is not True
    ):
        raise SmokeFailure("verification_contract_failed")
    if receipt.get("mode") != "preview":
        raise SmokeFailure("preview_contract_failed")

    return {
        "field": request.get("field"),
        "operation": request.get("operation"),
        "context_mode": provenance.get("mode"),
        "upstream_count": len(upstream),
        "downstream_count": len(downstream),
        "deterministic_score": risk.get("score"),
        "artifact_count": len(files),
        "static_checks_passed": passed_checks,
        "static_checks_total": len(checks),
        "warehouse_status": warehouse.get("status"),
        "warehouse_rows_evaluated": warehouse.get("rows_evaluated"),
        "warehouse_populated_row_count": warehouse.get("populated_row_count"),
        "warehouse_unsafe_row_count": warehouse.get("unsafe_row_count"),
        "receipt_mode": receipt.get("mode"),
    }


async def run_competition_smoke(
    settings: Settings,
    options: SmokeOptions,
    *,
    context_port: DataHubContextPort | None = None,
    warehouse_port: WarehouseValidationPort | None = None,
    http_port: HttpPort = _default_http_port,
) -> dict[str, object]:
    """Exercise discovery, analysis, policy, and preview through the HTTP API."""

    if options.datahub_only and options.require_warehouse:
        raise SmokeFailure("invalid_smoke_options")
    if options.require_live_datahub and settings.mode not in {Mode.AUTO, Mode.LIVE}:
        raise SmokeFailure("live_datahub_configuration_incomplete")
    if options.require_live_datahub and not settings.live_context_enabled:
        raise SmokeFailure("live_datahub_configuration_incomplete")

    with tempfile.TemporaryDirectory(prefix="changesafe-competition-") as temp_dir:
        active_settings = _effective_settings(
            settings,
            options,
            database_path=Path(temp_dir) / "smoke.db",
        )
        active_warehouse = None if options.datahub_only else warehouse_port
        app = create_app(
            settings=active_settings,
            context_port=context_port,
            warehouse_port=active_warehouse,
            web_dist=Path(temp_dir) / "no-web",
        )
        operation_summaries: list[dict[str, object]] = []
        async with app.router.lifespan_context(app), http_port(app) as client:
            schema_response = await client.get(
                "/api/schema-fields",
                params={"asset_urn": DEMO_TARGET_URN},
            )
            if schema_response.status_code != 200:
                raise SmokeFailure("catalog_read_failed")
            catalog = _validate_catalog(schema_response.json())
            for request in _select_requests(catalog):
                created = await client.post("/api/runs", json=request)
                if created.status_code != 202:
                    raise SmokeFailure("api_contract_failed")
                run_id = created.json().get("run_id")
                if not isinstance(run_id, str):
                    raise SmokeFailure("api_contract_failed")
                run = await _wait_for_run(client, run_id)
                if run.get("state") != "awaiting_approval":
                    raise SmokeFailure("analysis_policy_failed")
                analysis = run.get("analysis")
                if not isinstance(analysis, dict):
                    raise SmokeFailure("api_contract_failed")
                provenance = analysis.get("context", {}).get("provenance", {})
                if (
                    options.require_live_datahub
                    and provenance.get("mode") != ContextMode.LIVE.value
                ):
                    raise SmokeFailure("live_provenance_failed")
                warehouse = analysis.get("warehouse_validation", {})
                expected_warehouse = (
                    "not_run"
                    if not active_settings.warehouse_validation_enabled
                    else "passed"
                )
                if warehouse.get("status") != expected_warehouse:
                    raise SmokeFailure("warehouse_policy_failed")
                approved = await client.post(f"/api/runs/{run_id}/approve")
                if approved.status_code != 200:
                    raise SmokeFailure("preview_contract_failed")
                operation_summaries.append(
                    _safe_operation_summary(run, approved.json())
                )

        return {
            "status": "passed",
            "schema_field_count": len(catalog.schema_fields),
            "operations": operation_summaries,
        }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the credential-safe ChangeSafe competition smoke."
    )
    parser.add_argument("--datahub-only", action="store_true")
    parser.add_argument("--require-live-datahub", action="store_true")
    parser.add_argument("--require-warehouse", action="store_true")
    return parser


def _load_settings(
    options: SmokeOptions,
    *,
    env_file: Path | str | object | None,
) -> Settings:
    values: dict[str, object] = {
        "public_pr_enabled": False,
        "public_writeback_enabled": False,
        "live_evidence_required": options.require_live_datahub,
    }
    if options.datahub_only:
        values.update(
            {
                "warehouse_validation_enabled": False,
                "warehouse_validation_required": False,
            }
        )
    elif options.require_warehouse:
        values.update(
            {
                "warehouse_validation_enabled": True,
                "warehouse_validation_required": True,
            }
        )
    if env_file is not _USE_NORMAL_ENV:
        values["_env_file"] = env_file
    try:
        settings = Settings(**values)
    except ValidationError as exc:
        status = (
            "warehouse_configuration_incomplete"
            if options.require_warehouse
            else "configuration_invalid"
        )
        raise SmokeFailure(status) from exc
    if options.require_warehouse and (
        settings.snowflake_private_key_path is None
        or not settings.snowflake_private_key_path.is_file()
    ):
        raise SmokeFailure("warehouse_configuration_incomplete")
    return settings


_USE_NORMAL_ENV = object()


def main(
    argv: list[str] | None = None,
    *,
    env_file: Path | str | object | None = _USE_NORMAL_ENV,
) -> int:
    args = _parser().parse_args(argv)
    options = SmokeOptions(
        datahub_only=args.datahub_only,
        require_live_datahub=args.require_live_datahub,
        require_warehouse=args.require_warehouse,
    )
    try:
        settings = _load_settings(options, env_file=env_file)
        summary = asyncio.run(run_competition_smoke(settings, options))
    except SmokeFailure as exc:
        print(json.dumps({"status": exc.status}, separators=(",", ":")))
        return 2
    except Exception:
        print(json.dumps({"status": "smoke_failed"}, separators=(",", ":")))
        return 2
    print(json.dumps(summary, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
