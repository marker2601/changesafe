from pathlib import Path

import pytest

from changesafe.context.base import ContextLoadError, DecisionWriteback
from changesafe.context.replay import ReplayDataHubContext
from changesafe.domain import ChangeOperation, ChangeRequest, ContextMode, RiskBand

TARGET = "urn:li:dataset:(urn:li:dataPlatform:dbt,analytics.dim_customers,PROD)"


def golden_change() -> ChangeRequest:
    return ChangeRequest(
        asset_urn=TARGET,
        operation=ChangeOperation.RENAME,
        field="customer_email",
        new_field="primary_email",
        old_type="STRING",
        new_type="STRING",
        source_commit="demo-unsafe-change",
        requested_by="demo-user",
    )


@pytest.mark.asyncio
async def test_replay_contract_finds_the_golden_blast_radius() -> None:
    port = ReplayDataHubContext.from_default()

    context = await port.load(golden_change())

    assert context.provenance.mode is ContextMode.SNAPSHOT
    assert len(context.provenance.snapshot_hash or "") == 64
    assert len(context.downstream_assets) == 4
    assert {asset.domain for asset in context.downstream_assets} == {
        "Analytics",
        "Marketing",
        "Support",
        "Executive Reporting",
    }
    assert context.usage_tier == "high"
    assert "urn:li:tag:PII" in context.field_tags


@pytest.mark.asyncio
async def test_replay_rejects_snapshot_checksum_drift(tmp_path: Path) -> None:
    snapshot = tmp_path / "context.json"
    checksum = tmp_path / "context.sha256"
    snapshot.write_text('{"target_urn":"tampered"}\n', encoding="utf-8")
    checksum.write_text("0" * 64 + "\n", encoding="utf-8")
    port = ReplayDataHubContext(snapshot, checksum)

    with pytest.raises(ContextLoadError, match="checksum"):
        await port.load(golden_change())


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
    )

    receipt = await port.writeback(decision)

    assert receipt.mode == "preview"
    assert receipt.label == "NOT WRITTEN — SNAPSHOT MODE"
    assert receipt.mutations == []
