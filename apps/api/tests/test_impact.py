import pytest

from changesafe.context.replay import ReplayDataHubContext
from changesafe.demo import golden_change
from changesafe.domain import (
    ChangeOperation,
    ChangeRequest,
    EvidenceConfidence,
    ImpactCategory,
    ImpactSeverity,
)
from changesafe.impact import classify_impacts


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("change", "phrase"),
    [
        (golden_change(), "Renaming cust_email to primary_email"),
        (
            ChangeRequest(
                asset_urn=golden_change().asset_urn,
                operation=ChangeOperation.REMOVE,
                field="cust_email",
                source_commit="showcase-ecommerce-safe-remove",
                requested_by="changesafe-demo",
            ),
            "Removing cust_email",
        ),
        (
            ChangeRequest(
                asset_urn=golden_change().asset_urn,
                operation=ChangeOperation.TYPE_CHANGE,
                field="cust_email",
                old_type="TEXT",
                new_type="VARCHAR(320)",
                source_commit="showcase-ecommerce-safe-type-change",
                requested_by="changesafe-demo",
            ),
            "Changing cust_email from TEXT to VARCHAR(320)",
        ),
    ],
)
async def test_impact_summaries_name_the_requested_operation(
    change: ChangeRequest, phrase: str
) -> None:
    context = await ReplayDataHubContext.from_default().load(change)

    impacts = classify_impacts(change, context)

    assert all(phrase in impact.summary for impact in impacts)
    if change.operation is not ChangeOperation.RENAME:
        assert all("during the rename" not in impact.summary for impact in impacts)


@pytest.mark.asyncio
async def test_official_demo_classifies_six_evidence_led_impacts() -> None:
    change = golden_change()
    context = await ReplayDataHubContext.from_default().load(change)

    impacts = classify_impacts(change, context)

    assert [impact.category for impact in impacts] == [
        ImpactCategory.DATA_INTEGRITY,
        ImpactCategory.PRIVACY_COMPLIANCE,
        ImpactCategory.OPERATIONAL_CONTINUITY,
        ImpactCategory.TRUST_DECISION_QUALITY,
        ImpactCategory.FINANCIAL_EXPOSURE,
        ImpactCategory.ORGANIZATIONAL_IMPACT,
    ]
    assert [impact.severity for impact in impacts] == [
        ImpactSeverity.CRITICAL,
        ImpactSeverity.INFORMATIONAL,
        ImpactSeverity.HIGH,
        ImpactSeverity.MEDIUM,
        ImpactSeverity.HIGH,
        ImpactSeverity.HIGH,
    ]
    assert impacts[0].confidence is EvidenceConfidence.DIRECT
    assert impacts[1].confidence is EvidenceConfidence.UNAVAILABLE
    assert impacts[4].confidence is EvidenceConfidence.INFERRED
    assert impacts[4].qualifier == "Potentially high, not quantified"
    assert all(impact.evidence_urns for impact in impacts)
    assert all(
        "$" not in f"{impact.summary} {impact.basis} {impact.qualifier or ''}"
        for impact in impacts
    )


@pytest.mark.asyncio
async def test_financial_impact_never_becomes_a_fabricated_amount() -> None:
    change = golden_change()
    context = await ReplayDataHubContext.from_default().load(change)
    sparse = context.model_copy(
        update={"usage_tier": "none", "queries": [], "downstream_assets": []}
    )

    financial = next(
        impact
        for impact in classify_impacts(change, sparse)
        if impact.category is ImpactCategory.FINANCIAL_EXPOSURE
    )

    assert financial.severity is ImpactSeverity.INFORMATIONAL
    assert financial.confidence is EvidenceConfidence.UNAVAILABLE
    assert financial.qualifier == "Not quantified from available metadata"
    assert financial.evidence_urns == [context.target_urn]


@pytest.mark.asyncio
async def test_none_usage_is_described_as_no_recorded_usage() -> None:
    context = await ReplayDataHubContext.from_default().load(golden_change())
    sparse = context.model_copy(
        update={"usage_tier": "none", "queries": [], "downstream_assets": []}
    )

    operational = next(
        impact
        for impact in classify_impacts(golden_change(), sparse)
        if impact.category is ImpactCategory.OPERATIONAL_CONTINUITY
    )

    assert operational.basis.startswith("DataHub has no recorded query usage")
