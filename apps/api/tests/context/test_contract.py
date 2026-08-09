from pathlib import Path

import pytest

from changesafe.context.base import ContextLoadError, DecisionWriteback
from changesafe.context.replay import ReplayDataHubContext
from changesafe.demo import DEMO_TARGET_URN, golden_change
from changesafe.domain import ContextMode, RiskBand

TARGET = DEMO_TARGET_URN


@pytest.mark.asyncio
async def test_replay_contract_finds_the_golden_dependencies() -> None:
    port = ReplayDataHubContext.from_default()

    context = await port.load(golden_change())

    assert context.provenance.mode is ContextMode.SNAPSHOT
    assert len(context.provenance.snapshot_hash or "") == 64
    assert len(context.downstream_assets) == 7
    assert {asset.domain for asset in context.downstream_assets if asset.domain} == {
        "Data Platform Team",
        "Ecommerce Operations",
    }
    assert context.usage_tier == "high"
    assert "urn:li:tag:b2fd91.PII_Data" in context.field_tags


@pytest.mark.asyncio
async def test_replay_uses_the_official_order_entry_scenario() -> None:
    port = ReplayDataHubContext.from_default()

    context = await port.load(golden_change())

    assert context.target_urn == (
        "urn:li:dataset:(urn:li:dataPlatform:dbt,"
        "b2fd91.ORDER_ENTRY_DB.analytics.order_details,PROD)"
    )
    assert context.target_name == "order_details"
    assert context.field == "cust_email"
    assert context.field_type in {"TEXT", "VARCHAR"}
    assert "urn:li:tag:b2fd91.PII_Data" in context.field_tags
    assert any(
        "powerbi" in asset.urn.lower() for asset in context.downstream_assets
    )
    assert any(
        "looker" in asset.urn.lower() for asset in context.downstream_assets
    )


@pytest.mark.asyncio
async def test_replay_rejects_snapshot_checksum_drift(tmp_path: Path) -> None:
    snapshot = tmp_path / "context.json"
    checksum = tmp_path / "context.sha256"
    snapshot.write_text('{"target_urn":"tampered"}\n', encoding="utf-8")
    checksum.write_text("0" * 64 + "\n", encoding="utf-8")
    port = ReplayDataHubContext(snapshot, checksum)

    with pytest.raises(ContextLoadError, match="checksum"):
        await port.load(golden_change())


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
