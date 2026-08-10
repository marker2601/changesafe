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
    LineagePrecision,
    Owner,
    RiskBand,
)
from changesafe.risk import band_for, score_change
from changesafe.sql_types import canonical_sql_type

TARGET = "urn:li:dataset:(urn:li:dataPlatform:dbt,analytics.dim_customers,PROD)"


def golden_change() -> ChangeRequest:
    return ChangeRequest(
        asset_urn=TARGET,
        operation=ChangeOperation.RENAME,
        field="customer_email",
        new_field="primary_email",
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
            lineage_precision=LineagePrecision.ENDPOINT_FIELD,
        ),
        AffectedAsset(
            urn="urn:li:dataset:(urn:li:dataPlatform:snowflake,marketing.campaign_audiences,PROD)",
            name="campaign_audiences",
            entity_type="dataset",
            domain="Marketing",
            field="customer_email",
            lineage_path=[TARGET, "urn:li:dataset:campaign_audiences"],
            lineage_precision=LineagePrecision.ENDPOINT_FIELD,
        ),
        AffectedAsset(
            urn="urn:li:dataset:(urn:li:dataPlatform:snowflake,support.customer_contact_queue,PROD)",
            name="customer_contact_queue",
            entity_type="dataset",
            domain="Support",
            field="customer_email",
            lineage_path=[TARGET, "urn:li:dataset:customer_contact_queue"],
            lineage_precision=LineagePrecision.ENDPOINT_FIELD,
        ),
        AffectedAsset(
            urn="urn:li:dashboard:(looker,customer_retention_dashboard)",
            name="customer_retention_dashboard",
            entity_type="dashboard",
            domain="Executive Reporting",
            field="customer_email",
            is_executive=True,
            lineage_path=[TARGET, "urn:li:dashboard:customer_retention_dashboard"],
            lineage_precision=LineagePrecision.ENDPOINT_FIELD,
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
        query_count=1,
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
            "old_type": None,
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


def test_type_change_rejects_old_type_that_disagrees_with_datahub() -> None:
    change = ChangeRequest(
        asset_urn=TARGET,
        operation=ChangeOperation.TYPE_CHANGE,
        field="customer_email",
        old_type="SMALLINT",
        new_type="FLOAT",
        source_commit="misstated-old-type",
        requested_by="demo-user",
    )

    with pytest.raises(ValueError, match="old_type does not match DataHub metadata"):
        score_change(change, golden_context())


def test_type_change_rejects_new_type_equal_to_datahub_type() -> None:
    with pytest.raises(ValueError, match="must differ"):
        ChangeRequest(
            asset_urn=TARGET,
            operation=ChangeOperation.TYPE_CHANGE,
            field="customer_email",
            old_type="VARCHAR",
            new_type="STRING",
            source_commit="no-op-type-change",
            requested_by="demo-user",
        )


@pytest.mark.parametrize(
    ("current_type", "new_type"),
    [
        ("VARCHAR(100)", "VARCHAR(200)"),
        ("NUMBER(10,0)", "NUMBER(18,0)"),
        ("NUMBER(10,2)", "NUMBER(12,4)"),
    ],
)
def test_parameter_widening_is_scored_from_datahub_type(
    current_type: str, new_type: str
) -> None:
    change = ChangeRequest(
        asset_urn=TARGET,
        operation=ChangeOperation.TYPE_CHANGE,
        field="customer_email",
        old_type=current_type,
        new_type=new_type,
        source_commit="widen-parameterized-type",
        requested_by="demo-user",
    )
    context = golden_context().model_copy(update={"field_type": current_type})

    result = score_change(change, context)

    assert result.factors[0].code == "base_compatible_type_change"
    assert result.factors[0].points == 15


@pytest.mark.parametrize(
    ("current_type", "new_type"),
    [
        ("VARCHAR(200)", "VARCHAR(100)"),
        ("NUMBER(18,0)", "NUMBER(10,0)"),
        ("NUMBER(12,4)", "NUMBER(10,2)"),
    ],
)
def test_parameter_narrowing_is_scored_as_incompatible(
    current_type: str, new_type: str
) -> None:
    change = ChangeRequest(
        asset_urn=TARGET,
        operation=ChangeOperation.TYPE_CHANGE,
        field="customer_email",
        old_type=current_type,
        new_type=new_type,
        source_commit="narrow-parameterized-type",
        requested_by="demo-user",
    )
    context = golden_context().model_copy(update={"field_type": current_type})

    result = score_change(change, context)

    assert result.factors[0].code == "base_type_change"
    assert result.factors[0].points == 35


@pytest.mark.parametrize(
    ("current_type", "new_type"),
    [("VARCHAR", "STRING"), ("STRING", "TEXT"), ("SMALLINT", "BIGINT")],
)
def test_snowflake_type_alias_no_ops_are_rejected(
    current_type: str, new_type: str
) -> None:
    with pytest.raises(ValueError, match="must differ"):
        ChangeRequest(
            asset_urn=TARGET,
            operation=ChangeOperation.TYPE_CHANGE,
            field="customer_email",
            old_type=current_type,
            new_type=new_type,
            source_commit="alias-no-op",
            requested_by="demo-user",
        )


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


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("NUMBER(1,0)", ("NUMBER", (1, 0))),
        ("NUMBER(38,37)", ("NUMBER", (38, 37))),
        ("VARCHAR(1)", ("VARCHAR", (1,))),
        ("VARCHAR(134217728)", ("VARCHAR", (134_217_728,))),
        ("BINARY(1)", ("BINARY", (1,))),
        ("BINARY(67108864)", ("BINARY", (67_108_864,))),
        ("TIMESTAMP_NTZ(0)", ("TIMESTAMP_NTZ", (0,))),
        ("TIMESTAMP_NTZ(9)", ("TIMESTAMP_NTZ", (9,))),
    ],
)
def test_canonical_sql_type_accepts_every_documented_parameter_boundary(
    value: str, expected: tuple[str, tuple[int, ...]]
) -> None:
    assert canonical_sql_type(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "NUMBER(0,0)",
        "NUMBER(39,0)",
        "NUMBER(1,2)",
        "NUMBER(38,38)",
        "VARCHAR(0)",
        "VARCHAR(134217729)",
        "BINARY(0)",
        "BINARY(67108865)",
        "TIMESTAMP_NTZ(10)",
        "BOOLEAN(1)",
    ],
)
def test_canonical_sql_type_rejects_values_outside_every_documented_bound(
    value: str,
) -> None:
    with pytest.raises(ValueError):
        canonical_sql_type(value)
