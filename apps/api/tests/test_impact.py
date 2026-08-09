import pytest

from changesafe.context.replay import ReplayDataHubContext
from changesafe.demo import golden_change
from changesafe.domain import (
    EvidenceConfidence,
    ImpactCategory,
    ImpactSeverity,
)
from changesafe.impact import classify_impacts


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
        ImpactSeverity.CRITICAL,
        ImpactSeverity.HIGH,
        ImpactSeverity.HIGH,
        ImpactSeverity.HIGH,
        ImpactSeverity.HIGH,
    ]
    assert impacts[0].confidence is EvidenceConfidence.DIRECT
    assert impacts[1].confidence is EvidenceConfidence.DIRECT
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
