"""Shared fail-closed approval policy for persisted analysis evidence."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from changesafe.domain import (
    ApprovalBlocker,
    ChangeRequest,
    ContextBundle,
    ContextMode,
    ValidationReport,
    WarehouseValidationResult,
    WarehouseValidationStatus,
    warehouse_evidence_incomplete_blocker,
    warehouse_passed_evidence_is_complete,
)


def evaluate_approval_policy(
    *,
    change: ChangeRequest,
    context: ContextBundle,
    validation: ValidationReport,
    warehouse: WarehouseValidationResult,
    require_live_evidence: bool,
    require_warehouse: bool,
    warehouse_max_age_seconds: int,
    expected_binding_fingerprint: str | None,
    now: datetime | None = None,
) -> list[ApprovalBlocker]:
    """Return every current approval blocker in deterministic policy order."""

    blockers: list[ApprovalBlocker] = []
    if not validation.passed:
        blockers.append(
            ApprovalBlocker(
                code="VERIFICATION_FAILED",
                message="Generated artifacts did not pass safety checks.",
            )
        )

    if context.target_urn != change.asset_urn or context.field != change.field:
        blockers.append(
            ApprovalBlocker(
                code="CONTEXT_IDENTITY_MISMATCH",
                message=(
                    "Metadata context does not match the requested asset and field."
                ),
            )
        )

    if require_live_evidence and context.provenance.mode is not ContextMode.LIVE:
        blockers.append(
            ApprovalBlocker(
                code="LIVE_EVIDENCE_REQUIRED",
                message="Live metadata evidence is required for approval.",
                retryable=True,
            )
        )

    if warehouse.status is WarehouseValidationStatus.NOT_RUN and require_warehouse:
        blockers.append(
            ApprovalBlocker(
                code="WAREHOUSE_EVIDENCE_REQUIRED",
                message="Warehouse validation evidence is required for approval.",
                retryable=True,
            )
        )
    elif warehouse.status is WarehouseValidationStatus.BLOCKED:
        blockers.append(
            ApprovalBlocker(
                code="WAREHOUSE_VALIDATION_FAILED",
                message="Warehouse validation did not pass.",
                retryable=any(
                    check.retryable for check in warehouse.checks if not check.passed
                ),
            )
        )

    incomplete_passed = (
        warehouse.status is WarehouseValidationStatus.PASSED
        and not warehouse_passed_evidence_is_complete(warehouse)
    )
    if incomplete_passed:
        blockers.append(warehouse_evidence_incomplete_blocker())

    if warehouse.operation is not change.operation or warehouse.field != change.field:
        blockers.append(
            ApprovalBlocker(
                code="WAREHOUSE_EVIDENCE_MISMATCH",
                message=(
                    "Warehouse evidence does not match the requested operation "
                    "and field."
                ),
            )
        )

    if (
        warehouse.status is WarehouseValidationStatus.PASSED
        and not incomplete_passed
        and (
            expected_binding_fingerprint is None
            or warehouse.binding_fingerprint != expected_binding_fingerprint
        )
    ):
        blockers.append(
            ApprovalBlocker(
                code="WAREHOUSE_CONFIGURATION_CHANGED",
                message=(
                    "The configured warehouse identity or relation changed after "
                    "validation."
                ),
                retryable=True,
            )
        )

    if (
        warehouse.status is WarehouseValidationStatus.PASSED
        and not incomplete_passed
    ):
        current_time = now or datetime.now(UTC)
        completed_at = warehouse.completed_at
        if (
            completed_at is None
            or completed_at.tzinfo is None
            or completed_at.utcoffset() is None
            or current_time.tzinfo is None
            or current_time.utcoffset() is None
        ) or completed_at > current_time:
            invalid_completion = True
        else:
            invalid_completion = (
                current_time.astimezone(UTC) - completed_at.astimezone(UTC)
                > timedelta(seconds=warehouse_max_age_seconds)
            )
        if invalid_completion:
            blockers.append(
                ApprovalBlocker(
                    code="WAREHOUSE_EVIDENCE_STALE",
                    message="Warehouse validation evidence is no longer current.",
                    retryable=True,
                )
            )

    return blockers


__all__ = ["evaluate_approval_policy"]
