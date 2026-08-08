from datetime import UTC, datetime

import pytest

from changesafe.domain import (
    AffectedAsset,
    ChangeOperation,
    ChangeRequest,
    ContextBundle,
    ContextMode,
    ContextProvenance,
    EvidenceRef,
    Owner,
    RiskBand,
)
from changesafe.risk import band_for, score_change

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


def golden_context() -> ContextBundle:
    downstream = [
        AffectedAsset(
            urn="urn:li:dataset:(urn:li:dataPlatform:snowflake,analytics.customer_360,PROD)",
            name="customer_360",
            entity_type="dataset",
            domain="Analytics",
            field="customer_email",
            lineage_path=[TARGET, "urn:li:dataset:customer_360"],
        ),
        AffectedAsset(
            urn="urn:li:dataset:(urn:li:dataPlatform:snowflake,marketing.campaign_audiences,PROD)",
            name="campaign_audiences",
            entity_type="dataset",
            domain="Marketing",
            field="customer_email",
            lineage_path=[TARGET, "urn:li:dataset:campaign_audiences"],
        ),
        AffectedAsset(
            urn="urn:li:dataset:(urn:li:dataPlatform:snowflake,support.customer_contact_queue,PROD)",
            name="customer_contact_queue",
            entity_type="dataset",
            domain="Support",
            field="customer_email",
            lineage_path=[TARGET, "urn:li:dataset:customer_contact_queue"],
        ),
        AffectedAsset(
            urn="urn:li:dashboard:(looker,customer_retention_dashboard)",
            name="customer_retention_dashboard",
            entity_type="dashboard",
            domain="Executive Reporting",
            field="customer_email",
            is_executive=True,
            lineage_path=[TARGET, "urn:li:dashboard:customer_retention_dashboard"],
        ),
    ]
    evidence = [
        EvidenceRef(
            urn=TARGET,
            kind="schema",
            label="customer_email STRING",
        ),
        EvidenceRef(
            urn="urn:li:tag:PII",
            kind="governance",
            label="PII",
        ),
        EvidenceRef(
            urn="urn:li:query:customer-email-usage",
            kind="usage",
            label="High usage",
        ),
        *[
            EvidenceRef(urn=asset.urn, kind="lineage", label=asset.name)
            for asset in downstream
        ],
    ]
    return ContextBundle(
        target_urn=TARGET,
        target_name="dim_customers",
        target_domain="Analytics",
        field="customer_email",
        field_type="STRING",
        downstream_assets=downstream,
        owners=[
            Owner(
                urn="urn:li:corpuser:data-platform",
                name="Data Platform",
                ownership_type="TECHNICAL_OWNER",
            ),
            Owner(
                urn="urn:li:corpuser:customer-analytics",
                name="Customer Analytics",
                ownership_type="DATA_OWNER",
            ),
        ],
        field_tags=["urn:li:tag:PII"],
        glossary_terms=["urn:li:glossaryTerm:CustomerEmail"],
        usage_tier="high",
        queries=["select customer_email from analytics.dim_customers"],
        evidence=evidence,
        provenance=ContextProvenance(
            mode=ContextMode.SNAPSHOT,
            retrieved_at=datetime(2026, 8, 6, tzinfo=UTC),
            adapter_version="1.0.0",
            snapshot_hash="a" * 64,
        ),
    )


def test_golden_rename_scores_ninety() -> None:
    result = score_change(golden_change(), golden_context())

    assert (result.score, result.band) == (90, RiskBand.CRITICAL)
    assert [factor.code for factor in result.factors] == [
        "base_rename",
        "downstream_assets",
        "executive_downstream",
        "governed_field",
        "high_usage",
        "cross_domain",
    ]
    assert [factor.points for factor in result.factors] == [25, 20, 15, 10, 10, 10]
    assert all(factor.evidence_urns for factor in result.factors)


def test_removal_without_downstream_context_is_medium() -> None:
    change = golden_change().model_copy(
        update={
            "operation": ChangeOperation.REMOVE,
            "new_field": None,
            "new_type": None,
        }
    )
    context = golden_context().model_copy(
        update={
            "downstream_assets": [],
            "field_tags": [],
            "glossary_terms": [],
            "usage_tier": "low",
            "target_domain": None,
            "owners": golden_context().owners,
        }
    )

    result = score_change(change, context)

    assert result.score == 40
    assert result.band is RiskBand.MEDIUM


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (0, RiskBand.LOW),
        (29, RiskBand.LOW),
        (30, RiskBand.MEDIUM),
        (59, RiskBand.MEDIUM),
        (60, RiskBand.HIGH),
        (79, RiskBand.HIGH),
        (80, RiskBand.CRITICAL),
        (100, RiskBand.CRITICAL),
    ],
)
def test_risk_band_boundaries(score: int, expected: RiskBand) -> None:
    assert band_for(score) is expected
