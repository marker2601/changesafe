import asyncio
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from scripts.capture_field_catalog import (
    build_recorded_catalog,
    capture_from_settings,
    capture_recorded_catalog,
)
from scripts.capture_snapshot import write_snapshot, write_snapshot_atomic
from scripts.check_secrets import SIGNATURES
from scripts.seed_datahub import (
    apply_seed,
    build_seed_proposals,
    build_seed_spec,
    verify_seed,
)

from changesafe.config import Mode
from changesafe.context import live
from changesafe.context.base import ContextLoadError
from changesafe.demo import DEMO_TARGET_URN
from changesafe.domain import (
    ChangeRequest,
    ContextBundle,
    ContextMode,
    ContextProvenance,
    EvidenceRef,
    SchemaCatalog,
    SchemaField,
)


class FakeCapturePort:
    def __init__(
        self,
        *,
        fail_on: str | None = None,
        close_failure: Exception | None = None,
    ) -> None:
        self.fail_on = fail_on
        self.close_failure = close_failure
        self.loaded_fields: list[str] = []
        self.closed = False
        self.schema = SchemaCatalog(
            target_urn=DEMO_TARGET_URN,
            target_name="order_details",
            schema_fields=[
                SchemaField(name="cust_email", data_type="TEXT", nullable=False),
                SchemaField(name="order_total", data_type="FLOAT", nullable=False),
            ],
            provenance=ContextProvenance(
                mode=ContextMode.LIVE,
                retrieved_at="2026-08-09T12:00:00Z",
                adapter_version="fake/1",
            ),
        )

    async def discover_schema(self, asset_urn: str) -> SchemaCatalog:
        assert asset_urn == DEMO_TARGET_URN
        return self.schema

    async def load(self, change: ChangeRequest) -> ContextBundle:
        self.loaded_fields.append(change.field)
        if change.field == self.fail_on:
            raise ContextLoadError("private-token later-field failure")
        schema_field = next(
            item for item in self.schema.schema_fields if item.name == change.field
        )
        return ContextBundle(
            target_urn=DEMO_TARGET_URN,
            target_name="order_details",
            target_domain="Data Platform Team",
            field=change.field,
            field_type=schema_field.data_type,
            schema_fields=self.schema.schema_fields,
            owners=[],
            structured_properties={"quality": [86.8]},
            evidence=[
                EvidenceRef(
                    urn=DEMO_TARGET_URN,
                    kind="schema",
                    label=f"{change.field} {schema_field.data_type}",
                )
            ],
            provenance=self.schema.provenance,
        )

    def close(self) -> None:
        self.closed = True
        if self.close_failure is not None:
            raise self.close_failure


def golden_fixture_context() -> ContextBundle:
    payload = json.loads(
        Path("fixtures/datahub/golden-context.json").read_text(encoding="utf-8")
    )
    if payload.get("snapshot_version") == 3:
        recorded = payload["fields"]["cust_email"]
        payload = {
            key: payload[key]
            for key in (
                "target_urn",
                "target_name",
                "target_domain",
                "schema_fields",
                "owners",
                "structured_properties",
                "provenance",
            )
        } | {"field": "cust_email", **recorded}
    payload["provenance"]["mode"] = "live"
    payload["provenance"]["snapshot_hash"] = None
    return ContextBundle.model_validate(payload)


def test_snapshot_capture_writes_canonical_redacted_bytes(tmp_path: Path) -> None:
    snapshot = tmp_path / "context.json"
    checksum = tmp_path / "context.sha256"
    write_snapshot(
        {
            "z": 2,
            "authorization": "Bearer private",
            "a": {"token": "secret", "urn": "urn:li:dataset:demo"},
        },
        snapshot,
        checksum,
    )

    raw = snapshot.read_bytes()
    parsed = json.loads(raw)

    assert parsed["authorization"] == "[REDACTED]"
    assert parsed["a"]["token"] == "[REDACTED]"
    assert raw.startswith(b'{\n  "a"')
    assert (
        checksum.read_text(encoding="ascii").split()[0]
        == hashlib.sha256(raw).hexdigest()
    )
    assert not snapshot.with_suffix(".json.tmp").exists()
    assert not checksum.with_suffix(".sha256.tmp").exists()


def test_snapshot_capture_atomic_helper_has_the_same_contract(tmp_path: Path) -> None:
    snapshot = tmp_path / "context.json"
    checksum = tmp_path / "context.sha256"

    digest = write_snapshot_atomic({"field": "cust_email"}, snapshot, checksum)

    assert digest == hashlib.sha256(snapshot.read_bytes()).hexdigest()
    assert checksum.read_text(encoding="ascii") == f"{digest}  context.json\n"


def test_catalog_capture_script_supports_direct_execution() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/capture_field_catalog.py", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "--target-urn" in result.stdout


def test_seed_cli_settings_failure_is_fixed_and_sensitive_safe(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from scripts import seed_datahub

    import changesafe.config as config_module

    sentinel = "SENSITIVE_SEED_SETTINGS_SENTINEL"

    def invalid_settings() -> None:
        raise ValueError(sentinel)

    monkeypatch.setattr(config_module, "Settings", invalid_settings)
    monkeypatch.setattr(sys, "argv", ["seed_datahub.py", "--verify-only"])

    with pytest.raises(SystemExit) as exc_info:
        seed_datahub.main()

    captured = capsys.readouterr()
    assert exc_info.value.code == 2
    assert "ChangeSafe startup configuration is invalid." in captured.err
    assert sentinel not in captured.out + captured.err


@pytest.mark.asyncio
async def test_catalog_capture_reads_every_field_sequentially(
    capsys: pytest.CaptureFixture[str],
) -> None:
    port = FakeCapturePort()

    catalog = await build_recorded_catalog(port, DEMO_TARGET_URN)

    assert port.loaded_fields == ["cust_email", "order_total"]
    assert catalog.snapshot_version == 3
    assert list(catalog.fields) == ["cust_email", "order_total"]
    assert catalog.fields["order_total"].field_type == "FLOAT"
    assert catalog.provenance.mode is ContextMode.SNAPSHOT
    assert catalog.provenance.snapshot_hash is None
    assert capsys.readouterr().out.splitlines() == [
        "Captured field 1/2",
        "Captured field 2/2",
    ]


@pytest.mark.asyncio
async def test_catalog_capture_does_not_replace_outputs_after_later_failure(
    tmp_path: Path,
) -> None:
    snapshot = tmp_path / "context.json"
    checksum = tmp_path / "context.sha256"
    snapshot.write_bytes(b"existing snapshot")
    checksum.write_bytes(b"existing checksum")
    port = FakeCapturePort(fail_on="order_total")

    with pytest.raises(ContextLoadError, match="later-field failure"):
        await capture_recorded_catalog(port, DEMO_TARGET_URN, snapshot, checksum)

    assert port.loaded_fields == ["cust_email", "order_total"]
    assert snapshot.read_bytes() == b"existing snapshot"
    assert checksum.read_bytes() == b"existing checksum"


@pytest.mark.asyncio
async def test_capture_cli_redacts_failures_and_closes_the_adapter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from scripts import capture_field_catalog

    port = FakeCapturePort(fail_on="order_total")
    settings = SimpleNamespace(mode=Mode.LIVE, live_context_enabled=True)
    monkeypatch.setattr(capture_field_catalog, "Settings", lambda: settings)
    monkeypatch.setattr(capture_field_catalog, "build_context_port", lambda _: port)

    result = await capture_from_settings(
        DEMO_TARGET_URN,
        tmp_path / "context.json",
        tmp_path / "context.sha256",
    )

    output = capsys.readouterr()
    assert result == 1
    assert port.closed is True
    assert "snapshot was not changed" in output.err
    assert "private-token" not in output.out + output.err


@pytest.mark.asyncio
async def test_capture_cli_requires_live_credentials_before_building_port(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts import capture_field_catalog

    settings = SimpleNamespace(mode=Mode.LIVE, live_context_enabled=False)
    monkeypatch.setattr(capture_field_catalog, "Settings", lambda: settings)

    def unexpected_factory(_settings: Any) -> None:
        raise AssertionError("factory must not run without live credentials")

    monkeypatch.setattr(capture_field_catalog, "build_context_port", unexpected_factory)

    result = await capture_from_settings(
        DEMO_TARGET_URN,
        tmp_path / "context.json",
        tmp_path / "context.sha256",
    )

    assert result == 2


@pytest.mark.asyncio
async def test_capture_cli_redacts_settings_validation_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from scripts import capture_field_catalog

    canary_secret = "github_" + "pat_" + ("S" * 40)

    def invalid_settings() -> None:
        raise ValueError(f"invalid credential {canary_secret}")

    monkeypatch.setattr(capture_field_catalog, "Settings", invalid_settings)

    result = await capture_from_settings(
        DEMO_TARGET_URN,
        tmp_path / "context.json",
        tmp_path / "context.sha256",
    )

    output = capsys.readouterr()
    assert result == 1
    assert "snapshot was not changed" in output.err
    assert canary_secret not in output.out + output.err


@pytest.mark.asyncio
async def test_capture_cli_redacts_close_failures_before_replacing_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from scripts import capture_field_catalog

    canary_secret = "sk-" + ("C" * 32)
    port = FakeCapturePort(
        close_failure=RuntimeError(f"cleanup rejected {canary_secret}")
    )
    settings = SimpleNamespace(mode=Mode.LIVE, live_context_enabled=True)
    snapshot = tmp_path / "context.json"
    checksum = tmp_path / "context.sha256"
    snapshot.write_bytes(b"existing snapshot")
    checksum.write_bytes(b"existing checksum")
    monkeypatch.setattr(capture_field_catalog, "Settings", lambda: settings)
    monkeypatch.setattr(capture_field_catalog, "build_context_port", lambda _: port)

    result = await capture_from_settings(
        DEMO_TARGET_URN,
        snapshot,
        checksum,
    )

    output = capsys.readouterr()
    assert result == 1
    assert port.closed is True
    assert snapshot.read_bytes() == b"existing snapshot"
    assert checksum.read_bytes() == b"existing checksum"
    assert "snapshot was not changed" in output.err
    assert canary_secret not in output.out + output.err


def test_seed_spec_contains_required_graph_and_governance_definitions() -> None:
    seed = build_seed_spec()

    assert seed["base_datapack"] == "showcase-ecommerce"
    assert seed["load_command"] == "datahub datapack load showcase-ecommerce"
    assert seed["field"] == "cust_email"
    assert seed["required_official_context"]["governance_tags"] == [
        "urn:li:tag:b2fd91.PII_Data"
    ]
    assert seed["overlay"]["tag"] == "urn:li:tag:ChangeSafe:Deprecating"
    assert set(seed["overlay"]["structured_properties"]) == {
        "urn:li:structuredProperty:changesafe.riskLevel",
        "urn:li:structuredProperty:changesafe.changeStatus",
        "urn:li:structuredProperty:changesafe.lastRunId",
    }


def test_seed_builds_stable_idempotent_metadata_upserts() -> None:
    proposals = build_seed_proposals()
    identities = [
        (proposal.entityUrn, proposal.aspectName) for proposal in proposals
    ]

    assert len(identities) == len(set(identities))
    assert (
        "urn:li:structuredProperty:changesafe.riskLevel",
        "propertyDefinition",
    ) in identities
    assert any(aspect == "queryProperties" for _, aspect in identities)
    assert not any(aspect == "schemaMetadata" for _, aspect in identities)
    assert not any(aspect == "upstreamLineage" for _, aspect in identities)
    assert not any(aspect == "ownership" for _, aspect in identities)

    class FakeEmitter:
        def __init__(self) -> None:
            self.emitted = []

        def emit(self, proposal) -> None:
            self.emitted.append((proposal.entityUrn, proposal.aspectName))

    emitter = FakeEmitter()
    apply_seed(emitter, proposals)
    apply_seed(emitter, proposals)

    assert emitter.emitted[: len(identities)] == identities
    assert emitter.emitted[len(identities) :] == identities


def test_seed_verification_closes_the_synchronous_live_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = golden_fixture_context().model_copy(
        update={"field_tags": ["urn:li:tag:b2fd91.PII_Data"]}
    )

    class FakeRunner:
        def __init__(self) -> None:
            self.closed = False

        def close(self) -> None:
            self.closed = True

    runner = FakeRunner()

    class FakePort:
        def __init__(self, **_kwargs: object) -> None:
            pass

        async def load(self, _change: object) -> ContextBundle:
            return context

        async def discover_schema(self, asset_urn: str) -> SchemaCatalog:
            if context.target_urn != asset_urn:
                raise ContextLoadError("Snapshot does not contain the requested asset")
            return SchemaCatalog(
                target_urn=context.target_urn,
                target_name=context.target_name,
                schema_fields=context.schema_fields,
                provenance=context.provenance,
            )

    monkeypatch.setattr(
        live.AgentContextToolRunner,
        "connect",
        staticmethod(lambda _url, _token: runner),
    )
    monkeypatch.setattr(live, "LiveDataHubContext", FakePort)

    asyncio.run(verify_seed("http://datahub.example", "private-token"))

    assert runner.closed is True


def test_secret_signatures_detect_fine_grained_github_tokens() -> None:
    token = b"github_" + b"pat_" + (b"A" * 40)

    assert SIGNATURES["GitHub fine-grained token"].search(token)
