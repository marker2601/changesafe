from datetime import UTC, datetime, timedelta

import pytest

from changesafe.demo import golden_change
from changesafe.domain import (
    AnalysisResult,
    ArtifactBundle,
    ArtifactFile,
    ContextBundle,
    ContextMode,
    ContextProvenance,
    RiskBand,
    RiskResult,
    ValidationCheck,
    ValidationReport,
    WarehouseCheck,
    WarehouseValidationMode,
    WarehouseValidationResult,
    WarehouseValidationStatus,
)
from changesafe.policy import evaluate_approval_policy

NOW = datetime(2026, 8, 9, 18, 0, tzinfo=UTC)
FINGERPRINT = "a" * 64


def context_for(mode: ContextMode = ContextMode.LIVE) -> ContextBundle:
    change = golden_change()
    return ContextBundle(
        target_urn=change.asset_urn,
        target_name="order_details",
        field=change.field,
        field_type="TEXT",
        provenance=ContextProvenance(
            mode=mode,
            retrieved_at=NOW - timedelta(seconds=30),
            adapter_version="policy-test",
            snapshot_hash="b" * 64 if mode is ContextMode.SNAPSHOT else None,
        ),
    )


def validation_report(*, passed: bool = True) -> ValidationReport:
    return ValidationReport(
        passed=passed,
        checks=[
            ValidationCheck(
                code="sealed_artifacts",
                label="Sealed artifacts",
                passed=passed,
                detail=(
                    "Artifacts match the verified manifest."
                    if passed
                    else "Artifacts do not match the verified manifest."
                ),
            )
        ],
    )


def warehouse_result(
    status: WarehouseValidationStatus,
    *,
    completed_at: datetime | None = NOW,
    relation_fingerprint: str | None = FINGERPRINT,
    retryable: bool = False,
) -> WarehouseValidationResult:
    change = golden_change()
    if status is WarehouseValidationStatus.NOT_RUN:
        return WarehouseValidationResult(
            status=status,
            mode=WarehouseValidationMode.NONE,
            environment_label="competition-non-production",
            operation=change.operation,
            field=change.field,
            aggregate_query_started=False,
        )
    passed = status is WarehouseValidationStatus.PASSED
    return WarehouseValidationResult(
        status=status,
        mode=WarehouseValidationMode.AGGREGATE,
        environment_label="competition-non-production",
        operation=change.operation,
        field=change.field,
        aggregate_query_started=True if passed else None,
        relation_fingerprint=relation_fingerprint,
        started_at=(completed_at - timedelta(seconds=1) if completed_at else None),
        completed_at=completed_at,
        rows_evaluated=20 if passed else None,
        populated_row_count=20 if passed else None,
        query_ids=["safe-query-id"] if completed_at else [],
        elapsed_ms=1_000 if completed_at else None,
        checks=[
            WarehouseCheck(
                code="aggregate_validation" if passed else "warehouse_timeout",
                label="Aggregate validation",
                passed=passed,
                retryable=retryable,
                detail=(
                    "Aggregate checks passed."
                    if passed
                    else "Warehouse validation timed out."
                ),
            )
        ],
    )


def evaluate(
    *,
    context: ContextBundle | None = None,
    validation: ValidationReport | None = None,
    warehouse: WarehouseValidationResult | None = None,
    require_live: bool = False,
    require_warehouse: bool = False,
    expected_relation_fingerprint: str | None = FINGERPRINT,
    now: datetime = NOW,
):
    return evaluate_approval_policy(
        change=golden_change(),
        context=context or context_for(),
        validation=validation or validation_report(),
        warehouse=warehouse
        or warehouse_result(WarehouseValidationStatus.PASSED),
        require_live_evidence=require_live,
        require_warehouse=require_warehouse,
        warehouse_max_age_seconds=900,
        expected_relation_fingerprint=expected_relation_fingerprint,
        now=now,
    )


@pytest.mark.parametrize(
    ("context_mode", "warehouse_status", "require_live", "require_warehouse", "codes"),
    [
        ("live", "passed", True, True, set()),
        ("snapshot", "passed", True, True, {"LIVE_EVIDENCE_REQUIRED"}),
        ("live", "not_run", True, True, {"WAREHOUSE_EVIDENCE_REQUIRED"}),
        ("live", "blocked", True, True, {"WAREHOUSE_VALIDATION_FAILED"}),
        ("snapshot", "not_run", False, False, set()),
    ],
)
def test_approval_policy_matrix(
    context_mode: str,
    warehouse_status: str,
    require_live: bool,
    require_warehouse: bool,
    codes: set[str],
) -> None:
    blockers = evaluate(
        context=context_for(ContextMode(context_mode)),
        warehouse=warehouse_result(WarehouseValidationStatus(warehouse_status)),
        require_live=require_live,
        require_warehouse=require_warehouse,
        expected_relation_fingerprint=(
            None if warehouse_status == "not_run" else FINGERPRINT
        ),
    )

    assert {item.code for item in blockers} == codes


@pytest.mark.parametrize(
    ("age_seconds", "expected_codes"),
    [
        (900, []),
        (901, ["WAREHOUSE_EVIDENCE_STALE"]),
    ],
)
def test_warehouse_freshness_uses_utc_completion_time_and_inclusive_boundary(
    age_seconds: int,
    expected_codes: list[str],
) -> None:
    blockers = evaluate(
        warehouse=warehouse_result(
            WarehouseValidationStatus.PASSED,
            completed_at=NOW - timedelta(seconds=age_seconds),
        )
    )

    assert [item.code for item in blockers] == expected_codes


def test_relation_fingerprint_drift_blocks_approval() -> None:
    blockers = evaluate(expected_relation_fingerprint="c" * 64)

    assert [item.code for item in blockers] == ["WAREHOUSE_RELATION_CHANGED"]


def test_passed_evidence_with_unknown_query_boundary_is_incomplete() -> None:
    legacy_unknown = warehouse_result(
        WarehouseValidationStatus.PASSED
    ).model_copy(update={"aggregate_query_started": None})

    blockers = evaluate(warehouse=legacy_unknown)

    assert [
        (item.code, item.message, item.retryable) for item in blockers
    ] == [
        (
            "WAREHOUSE_EVIDENCE_INCOMPLETE",
            "Warehouse validation evidence is incomplete.",
            False,
        )
    ]


def test_passed_evidence_requires_a_current_operator_relation() -> None:
    evidence_without_relation = warehouse_result(
        WarehouseValidationStatus.PASSED,
        relation_fingerprint=None,
    )

    blockers = evaluate(
        warehouse=evidence_without_relation,
        expected_relation_fingerprint=None,
    )

    assert [item.code for item in blockers] == ["WAREHOUSE_RELATION_CHANGED"]


def test_static_validation_failure_is_the_first_policy_blocker() -> None:
    mismatched_context = context_for(ContextMode.SNAPSHOT).model_copy(
        update={"target_urn": "urn:li:dataset:mismatched", "field": "other_field"}
    )
    mismatched_warehouse = warehouse_result(
        WarehouseValidationStatus.PASSED,
        completed_at=NOW - timedelta(seconds=901),
    ).model_copy(update={"field": "other_field"})

    blockers = evaluate(
        context=mismatched_context,
        validation=validation_report(passed=False),
        warehouse=mismatched_warehouse,
        require_live=True,
        expected_relation_fingerprint="c" * 64,
    )

    assert [item.code for item in blockers] == [
        "VERIFICATION_FAILED",
        "CONTEXT_IDENTITY_MISMATCH",
        "LIVE_EVIDENCE_REQUIRED",
        "WAREHOUSE_EVIDENCE_MISMATCH",
        "WAREHOUSE_RELATION_CHANGED",
        "WAREHOUSE_EVIDENCE_STALE",
    ]


@pytest.mark.parametrize(
    ("update", "expected_code"),
    [
        ({"target_urn": "urn:li:dataset:mismatched"}, "CONTEXT_IDENTITY_MISMATCH"),
        ({"field": "other_field"}, "CONTEXT_IDENTITY_MISMATCH"),
    ],
)
def test_request_context_identity_is_rechecked(
    update: dict[str, str], expected_code: str
) -> None:
    blockers = evaluate(context=context_for().model_copy(update=update))

    assert [item.code for item in blockers] == [expected_code]


def test_blocked_warehouse_evidence_preserves_retryability() -> None:
    blockers = evaluate(
        warehouse=warehouse_result(
            WarehouseValidationStatus.BLOCKED,
            retryable=True,
        )
    )

    assert [(item.code, item.retryable) for item in blockers] == [
        ("WAREHOUSE_VALIDATION_FAILED", True)
    ]


def test_pre_upgrade_default_warehouse_result_fails_current_policy() -> None:
    analysis = AnalysisResult(
        context=context_for(),
        risk=RiskResult(
            score=0,
            band=RiskBand.LOW,
            factors=[],
            recommended_strategy="Proceed.",
        ),
        artifacts=ArtifactBundle(
            files={
                "migration.sql": ArtifactFile(
                    path="migration.sql", content="select 1\n"
                )
            }
        ),
        validation=validation_report(),
        publication_eligible=True,
    )

    blockers = evaluate(
        warehouse=analysis.warehouse_validation,
        expected_relation_fingerprint=None,
    )

    assert [item.code for item in blockers] == ["WAREHOUSE_EVIDENCE_MISMATCH"]
