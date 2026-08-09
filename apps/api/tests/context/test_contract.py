import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from changesafe.context.base import ContextLoadError, DecisionWriteback
from changesafe.context.replay import ReplayDataHubContext
from changesafe.demo import DEMO_TARGET_URN, golden_change
from changesafe.domain import ContextMode, LineagePrecision, RiskBand

TARGET = DEMO_TARGET_URN


def write_catalog(tmp_path: Path, payload: dict[str, Any]) -> ReplayDataHubContext:
    snapshot = tmp_path / "context.json"
    checksum = tmp_path / "context.sha256"
    raw = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
    snapshot.write_bytes(raw)
    checksum.write_text(
        f"{hashlib.sha256(raw).hexdigest()}  {snapshot.name}\n",
        encoding="ascii",
    )
    return ReplayDataHubContext(snapshot, checksum)


def minimal_catalog() -> dict[str, Any]:
    field_context = {
        "field_type": "TEXT",
        "upstream_assets": [],
        "downstream_assets": [],
        "field_tags": [],
        "glossary_terms": [],
        "usage_tier": "none",
        "queries": [],
        "evidence": [],
        "tool_evidence": [],
    }
    return {
        "snapshot_version": 2,
        "target_urn": TARGET,
        "target_name": "order_details",
        "target_domain": None,
        "schema_fields": [
            {"name": "cust_email", "data_type": "TEXT", "nullable": False}
        ],
        "owners": [],
        "structured_properties": {},
        "fields": {"cust_email": field_context},
        "provenance": {
            "mode": "snapshot",
            "retrieved_at": "2026-08-08T20:00:00Z",
            "adapter_version": "test/1",
        },
    }


@pytest.mark.asyncio
async def test_replay_discovery_returns_the_checksummed_schema() -> None:
    catalog = await ReplayDataHubContext.from_default().discover_schema(TARGET)

    assert catalog.target_urn == TARGET
    assert catalog.target_name == "order_details"
    assert len(catalog.schema_fields) == 55
    assert [(field.name, field.data_type) for field in catalog.schema_fields[:3]] == [
        ("order_id", "NUMBER"),
        ("order_date", "TEXT"),
        ("order_mode", "TEXT"),
    ]
    assert catalog.provenance.mode is ContextMode.SNAPSHOT
    assert len(catalog.provenance.snapshot_hash or "") == 64


@pytest.mark.asyncio
async def test_replay_discovery_rejects_a_different_asset() -> None:
    port = ReplayDataHubContext.from_default()

    with pytest.raises(ContextLoadError, match="requested asset"):
        await port.discover_schema("urn:li:dataset:other")


@pytest.mark.asyncio
async def test_replay_contract_finds_the_golden_dependencies() -> None:
    port = ReplayDataHubContext.from_default()

    context = await port.load(golden_change())

    assert context.provenance.mode is ContextMode.SNAPSHOT
    assert len(context.provenance.snapshot_hash or "") == 64
    assert len(context.upstream_assets) == 6
    assert len(context.downstream_assets) == 25
    assert [asset.lineage_degree for asset in context.upstream_assets] == [
        1,
        4,
        2,
        4,
        3,
        3,
    ]
    assert [asset.lineage_degree for asset in context.downstream_assets] == [
        3,
        1,
        2,
        2,
        2,
        2,
        2,
        2,
        2,
        2,
        5,
        3,
        4,
        4,
        4,
        4,
        5,
        4,
        4,
        4,
        4,
        3,
        3,
        3,
        3,
    ]
    assert {asset.domain for asset in context.downstream_assets if asset.domain} == {
        "Data Platform Team",
        "Ecommerce Operations",
        "Marketing",
    }
    assert context.usage_tier == "high"
    assert context.field_tags == []
    assert context.glossary_terms == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "expected_type"),
    [("cust_email", "TEXT"), ("order_total", "FLOAT"), ("order_status", "NUMBER")],
)
async def test_replay_builds_a_field_scoped_context(
    field: str, expected_type: str
) -> None:
    change = golden_change().model_copy(
        update={"field": field, "new_field": f"preferred_{field}"}
    )
    context = await ReplayDataHubContext.from_default().load(change)

    assert context.field == field
    assert context.field_type == expected_type
    for asset in [*context.upstream_assets, *context.downstream_assets]:
        if asset.field is None:
            assert asset.lineage_precision is LineagePrecision.DATASET_LEVEL
        else:
            assert asset.lineage_precision is not LineagePrecision.DATASET_LEVEL
    if field == "order_total":
        derived = next(
            asset
            for asset in context.downstream_assets
            if asset.field == "AVERAGE_ORDER_VALUE"
        )
        assert derived.lineage_precision is LineagePrecision.ENDPOINT_FIELD
    if field != "cust_email":
        scoped_text = json.dumps(
            {
                "field_tags": context.field_tags,
                "glossary_terms": context.glossary_terms,
                "queries": context.queries,
                "evidence": [
                    item.model_dump(mode="json") for item in context.evidence
                ],
                "upstream": [
                    item.model_dump(mode="json") for item in context.upstream_assets
                ],
                "downstream": [
                    item.model_dump(mode="json") for item in context.downstream_assets
                ],
            }
        )
        assert "cust_email" not in scoped_text


@pytest.mark.asyncio
@pytest.mark.parametrize("unexpected", ["missing", "extra"])
async def test_replay_rejects_field_contexts_that_do_not_match_schema(
    tmp_path: Path, unexpected: str
) -> None:
    payload = minimal_catalog()
    if unexpected == "missing":
        payload["fields"] = {}
    else:
        payload["fields"]["order_total"] = payload["fields"]["cust_email"]
    port = write_catalog(tmp_path, payload)

    with pytest.raises(ContextLoadError, match="contract validation"):
        await port.discover_schema(TARGET)


@pytest.mark.asyncio
async def test_replay_rejects_duplicate_schema_field_names(tmp_path: Path) -> None:
    payload = minimal_catalog()
    payload["schema_fields"].append(
        {"name": "CUST_EMAIL", "data_type": "TEXT", "nullable": False}
    )
    payload["fields"]["CUST_EMAIL"] = payload["fields"]["cust_email"]
    port = write_catalog(tmp_path, payload)

    with pytest.raises(ContextLoadError, match="contract validation"):
        await port.discover_schema(TARGET)


@pytest.mark.asyncio
async def test_replay_rejects_an_unknown_selected_field(tmp_path: Path) -> None:
    port = write_catalog(tmp_path, minimal_catalog())
    change = golden_change().model_copy(
        update={"field": "order_total", "new_field": "preferred_order_total"}
    )

    with pytest.raises(ContextLoadError, match="requested field"):
        await port.load(change)


@pytest.mark.asyncio
async def test_replay_rejects_snapshot_checksum_drift(tmp_path: Path) -> None:
    snapshot = tmp_path / "context.json"
    checksum = tmp_path / "context.sha256"
    snapshot.write_text('{"target_urn":"tampered"}\n', encoding="utf-8")
    checksum.write_text("0" * 64 + "\n", encoding="utf-8")
    port = ReplayDataHubContext(snapshot, checksum)

    with pytest.raises(ContextLoadError, match="checksum"):
        await port.discover_schema(TARGET)


def test_replay_default_paths_can_be_overridden_for_packaged_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot = tmp_path / "packaged-context.json"
    checksum = tmp_path / "packaged-context.sha256"
    monkeypatch.setenv("CHANGESAFE_SNAPSHOT_PATH", str(snapshot))
    monkeypatch.setenv("CHANGESAFE_SNAPSHOT_CHECKSUM_PATH", str(checksum))

    port = ReplayDataHubContext.from_default()

    assert port.snapshot_path == snapshot
    assert port.checksum_path == checksum


@pytest.mark.asyncio
async def test_replay_writeback_is_an_explicit_non_mutating_preview() -> None:
    port = ReplayDataHubContext.from_default()
    decision = DecisionWriteback(
        run_id="0198f2b8-a68d-7af3-8958-cb18c7337e91",
        change=golden_change(),
        risk_score=90,
        risk_band=RiskBand.CRITICAL,
        artifact_hash="b" * 64,
        approved_at="2026-08-08T12:00:00Z",
        idempotency_key="f" * 64,
    )

    receipt = await port.writeback(decision)

    assert receipt.mode == "preview"
    assert receipt.label == "NOT WRITTEN — SNAPSHOT MODE"
    assert receipt.mutations == []
