import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import changesafe.orchestrator as orchestrator_module
from changesafe.context.base import ContextLoadError
from changesafe.context.replay import ReplayDataHubContext
from changesafe.demo import golden_change
from changesafe.domain import (
    ChangeRequest,
    ImpactCategory,
    RunState,
    ValidationCheck,
    ValidationReport,
    WarehouseCheck,
    WarehouseValidationMode,
    WarehouseValidationResult,
    WarehouseValidationStatus,
)
from changesafe.generation.service import ArtifactGenerationService
from changesafe.orchestrator import ChangeSafeOrchestrator
from changesafe.store import RunStore
from changesafe.warehouse.base import WarehouseValidationError
from changesafe.warehouse.queries import fingerprint_relation

WAREHOUSE_RELATION = "SAFE_DB.SAFE_SCHEMA.ORDER_DETAILS"


def passed_warehouse_result() -> WarehouseValidationResult:
    now = datetime.now(UTC)
    change = golden_change()
    return WarehouseValidationResult(
        status=WarehouseValidationStatus.PASSED,
        mode=WarehouseValidationMode.AGGREGATE,
        environment_label="competition-non-production",
        operation=change.operation,
        field=change.field,
        relation_fingerprint=fingerprint_relation(WAREHOUSE_RELATION),
        started_at=now - timedelta(seconds=1),
        completed_at=now,
        rows_evaluated=20,
        populated_row_count=20,
        query_ids=["safe-query-id"],
        elapsed_ms=1_000,
        checks=[
            WarehouseCheck(
                code="aggregate_validation",
                label="Aggregate validation",
                passed=True,
                detail="Aggregate checks passed.",
            )
        ],
    )


def blocked_warehouse_result() -> WarehouseValidationResult:
    now = datetime.now(UTC)
    change = golden_change()
    return WarehouseValidationResult(
        status=WarehouseValidationStatus.BLOCKED,
        mode=WarehouseValidationMode.AGGREGATE,
        environment_label="competition-non-production",
        operation=change.operation,
        field=change.field,
        relation_fingerprint=fingerprint_relation(WAREHOUSE_RELATION),
        started_at=now - timedelta(seconds=1),
        completed_at=now,
        elapsed_ms=1_000,
        checks=[
            WarehouseCheck(
                code="unsafe_conversion",
                label="Aggregate validation",
                passed=False,
                detail="Some populated rows cannot be converted safely.",
            )
        ],
    )


def not_run_warehouse_result() -> WarehouseValidationResult:
    change = golden_change()
    return WarehouseValidationResult(
        status=WarehouseValidationStatus.NOT_RUN,
        mode=WarehouseValidationMode.NONE,
        environment_label="competition-non-production",
        operation=change.operation,
        field=change.field,
    )


class FakeWarehousePort:
    def __init__(self, result: WarehouseValidationResult) -> None:
        self.result = result
        self.calls = 0

    async def validate(self, change: ChangeRequest, context):
        self.calls += 1
        assert change.field == context.field
        return self.result

    async def close(self) -> None:
        return


class FailingWarehousePort:
    def __init__(self) -> None:
        self.calls = 0

    async def validate(self, change: ChangeRequest, context):
        del change, context
        self.calls += 1
        raise WarehouseValidationError(
            "warehouse_timeout",
            "Warehouse validation timed out.",
            retryable=True,
        )

    async def close(self) -> None:
        return


class HangingWarehousePort:
    def __init__(self) -> None:
        self.calls = 0
        self.cancelled = False

    async def validate(self, change: ChangeRequest, context):
        del change, context
        self.calls += 1
        try:
            await asyncio.Event().wait()
        finally:
            self.cancelled = True

    async def close(self) -> None:
        return


class UnavailableContext:
    async def load(self, change: ChangeRequest):
        del change
        raise ContextLoadError("live context unavailable")


@pytest.mark.asyncio
async def test_golden_pipeline_reaches_awaiting_approval(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.db")
    await store.initialize()
    orchestrator = ChangeSafeOrchestrator(
        store=store,
        context_port=ReplayDataHubContext.from_default(),
        generator=ArtifactGenerationService(),
    )
    run = await store.create(golden_change())

    result = await orchestrator.analyze(run.run_id)

    assert result.state is RunState.AWAITING_APPROVAL
    assert result.analysis is not None
    assert result.analysis.risk.score == 85
    assert result.analysis.validation.passed is True
    assert result.analysis.publication_eligible is True
    assert result.analysis.warehouse_validation.status is (
        WarehouseValidationStatus.NOT_RUN
    )
    assert result.analysis.warehouse_validation.operation is run.request.operation
    assert result.analysis.warehouse_validation.field == run.request.field
    assert result.analysis.approval_blockers == []
    assert len(result.analysis.artifacts.files) == 7
    assert [impact.category for impact in result.analysis.impacts] == list(
        ImpactCategory
    )
    assert [event.state for event in await store.events(run.run_id)] == [
        RunState.CREATED,
        RunState.LOADING_CONTEXT,
        RunState.SCORING_RISK,
        RunState.GENERATING,
        RunState.VALIDATING,
        RunState.AWAITING_APPROVAL,
    ]
    events = await store.events(run.run_id)
    assert [event.public_message for event in events[1:]] == [
        "Reading the existing data contract",
        "Classifying business and technical impact",
        "Preparing a compatible migration",
        "Proving the generated change is safe",
        "Waiting for the accountable owner",
    ]


@pytest.mark.asyncio
async def test_required_warehouse_pass_reaches_awaiting_approval(
    tmp_path: Path,
) -> None:
    store = RunStore(tmp_path / "required-pass.db")
    warehouse = FakeWarehousePort(passed_warehouse_result())
    orchestrator = ChangeSafeOrchestrator(
        store=store,
        context_port=ReplayDataHubContext.from_default(),
        generator=ArtifactGenerationService(),
        warehouse_port=warehouse,
        require_warehouse=True,
        warehouse_target_map={golden_change().asset_urn: WAREHOUSE_RELATION},
    )
    run = await store.create(golden_change())

    result = await orchestrator.analyze(run.run_id)

    assert result.state is RunState.AWAITING_APPROVAL
    assert result.analysis is not None
    assert result.analysis.publication_eligible is True
    assert result.analysis.warehouse_validation.status is (
        WarehouseValidationStatus.PASSED
    )
    assert result.analysis.approval_blockers == []
    assert warehouse.calls == 1
    assert [event.state for event in await store.events(run.run_id)][-3:] == [
        RunState.VALIDATING,
        RunState.VALIDATING_WAREHOUSE,
        RunState.AWAITING_APPROVAL,
    ]


@pytest.mark.asyncio
async def test_required_missing_warehouse_preserves_analysis_in_failed(
    tmp_path: Path,
) -> None:
    store = RunStore(tmp_path / "required-missing.db")
    orchestrator = ChangeSafeOrchestrator(
        store=store,
        context_port=ReplayDataHubContext.from_default(),
        generator=ArtifactGenerationService(),
        require_warehouse=True,
    )
    run = await store.create(golden_change())

    result = await orchestrator.analyze(run.run_id)

    assert result.state is RunState.FAILED
    assert result.analysis is not None
    assert result.analysis.publication_eligible is False
    assert result.analysis.warehouse_validation.status is (
        WarehouseValidationStatus.NOT_RUN
    )
    assert [item.code for item in result.analysis.approval_blockers] == [
        "WAREHOUSE_EVIDENCE_REQUIRED"
    ]
    assert result.error is not None
    assert result.error.code == "WAREHOUSE_EVIDENCE_REQUIRED"


@pytest.mark.asyncio
async def test_failed_warehouse_result_preserves_analysis_in_failed(
    tmp_path: Path,
) -> None:
    store = RunStore(tmp_path / "warehouse-blocked.db")
    warehouse = FakeWarehousePort(blocked_warehouse_result())
    orchestrator = ChangeSafeOrchestrator(
        store=store,
        context_port=ReplayDataHubContext.from_default(),
        generator=ArtifactGenerationService(),
        warehouse_port=warehouse,
        warehouse_target_map={golden_change().asset_urn: WAREHOUSE_RELATION},
    )
    run = await store.create(golden_change())

    result = await orchestrator.analyze(run.run_id)

    assert result.state is RunState.FAILED
    assert result.analysis is not None
    assert result.analysis.warehouse_validation.status is (
        WarehouseValidationStatus.BLOCKED
    )
    assert result.analysis.publication_eligible is False
    assert result.error is not None
    assert result.error.code == "WAREHOUSE_VALIDATION_FAILED"
    assert warehouse.calls == 1


@pytest.mark.asyncio
async def test_optional_called_port_not_run_is_retryable_blocked_evidence(
    tmp_path: Path,
) -> None:
    store = RunStore(tmp_path / "optional-not-run.db")
    warehouse = FakeWarehousePort(not_run_warehouse_result())
    orchestrator = ChangeSafeOrchestrator(
        store=store,
        context_port=ReplayDataHubContext.from_default(),
        generator=ArtifactGenerationService(),
        warehouse_port=warehouse,
        require_warehouse=False,
        warehouse_target_map={golden_change().asset_urn: WAREHOUSE_RELATION},
    )
    run = await store.create(golden_change())

    result = await orchestrator.analyze(run.run_id)

    assert result.state is RunState.FAILED
    assert result.analysis is not None
    assert result.analysis.publication_eligible is False
    assert result.analysis.warehouse_validation.status is (
        WarehouseValidationStatus.BLOCKED
    )
    check = result.analysis.warehouse_validation.checks[0]
    assert (check.code, check.detail, check.retryable) == (
        "warehouse_not_run",
        "Warehouse validation returned no execution evidence.",
        True,
    )
    assert [item.code for item in result.analysis.approval_blockers] == [
        "WAREHOUSE_VALIDATION_FAILED"
    ]
    assert result.error is not None
    assert (result.error.code, result.error.retryable) == (
        "WAREHOUSE_VALIDATION_FAILED",
        True,
    )
    assert warehouse.calls == 1


@pytest.mark.asyncio
async def test_warehouse_exception_becomes_blocked_evidence_instead_of_not_run(
    tmp_path: Path,
) -> None:
    store = RunStore(tmp_path / "warehouse-timeout.db")
    warehouse = FailingWarehousePort()
    orchestrator = ChangeSafeOrchestrator(
        store=store,
        context_port=ReplayDataHubContext.from_default(),
        generator=ArtifactGenerationService(),
        warehouse_port=warehouse,
        require_warehouse=True,
        warehouse_target_map={golden_change().asset_urn: WAREHOUSE_RELATION},
    )
    run = await store.create(golden_change())

    result = await orchestrator.analyze(run.run_id)

    assert result.state is RunState.FAILED
    assert result.analysis is not None
    assert result.analysis.warehouse_validation.status is (
        WarehouseValidationStatus.BLOCKED
    )
    assert result.analysis.warehouse_validation.checks[0].code == "warehouse_timeout"
    assert result.analysis.approval_blockers[0].retryable is True
    assert result.error is not None
    assert result.error.retryable is True
    assert warehouse.calls == 1


@pytest.mark.asyncio
async def test_orchestrator_timeout_becomes_retryable_blocked_evidence(
    tmp_path: Path,
) -> None:
    store = RunStore(tmp_path / "orchestrator-timeout.db")
    warehouse = HangingWarehousePort()
    orchestrator = ChangeSafeOrchestrator(
        store=store,
        context_port=ReplayDataHubContext.from_default(),
        generator=ArtifactGenerationService(),
        warehouse_port=warehouse,
        require_warehouse=True,
        warehouse_timeout_seconds=0.01,
        warehouse_target_map={golden_change().asset_urn: WAREHOUSE_RELATION},
    )
    run = await store.create(golden_change())

    result = await orchestrator.analyze(run.run_id)

    assert result.state is RunState.FAILED
    assert result.analysis is not None
    assert result.analysis.warehouse_validation.status is (
        WarehouseValidationStatus.BLOCKED
    )
    assert result.analysis.warehouse_validation.checks[0].code == "warehouse_timeout"
    assert result.analysis.approval_blockers[0].retryable is True
    assert warehouse.calls == 1
    assert warehouse.cancelled is True


@pytest.mark.asyncio
async def test_static_verification_failure_never_calls_warehouse(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = RunStore(tmp_path / "static-failure.db")
    warehouse = FakeWarehousePort(passed_warehouse_result())
    orchestrator = ChangeSafeOrchestrator(
        store=store,
        context_port=ReplayDataHubContext.from_default(),
        generator=ArtifactGenerationService(),
        warehouse_port=warehouse,
        warehouse_target_map={golden_change().asset_urn: WAREHOUSE_RELATION},
    )
    monkeypatch.setattr(
        orchestrator_module,
        "verify_artifacts",
        lambda *_args: ValidationReport(
            passed=False,
            checks=[
                ValidationCheck(
                    code="sealed_artifacts",
                    label="Sealed artifacts",
                    passed=False,
                    detail="The artifact seal does not match.",
                )
            ],
        ),
    )
    run = await store.create(golden_change())

    result = await orchestrator.analyze(run.run_id)

    assert result.state is RunState.FAILED
    assert result.analysis is not None
    assert result.analysis.approval_blockers[0].code == "VERIFICATION_FAILED"
    assert warehouse.calls == 0
    assert RunState.VALIDATING_WAREHOUSE not in {
        event.state for event in await store.events(run.run_id)
    }


@pytest.mark.asyncio
async def test_explicit_snapshot_fallback_is_non_publishable_when_live_is_required(
    tmp_path: Path,
) -> None:
    store = RunStore(tmp_path / "required-live-fallback.db")
    orchestrator = ChangeSafeOrchestrator(
        store=store,
        context_port=UnavailableContext(),
        snapshot_context_port=ReplayDataHubContext.from_default(),
        generator=ArtifactGenerationService(),
        require_live_evidence=True,
    )
    run = await store.create(golden_change())
    fallback = await orchestrator.analyze(run.run_id)

    assert fallback.state is RunState.CONTEXT_FALLBACK_REQUIRED
    await orchestrator.continue_with_snapshot(run.run_id)
    await orchestrator.wait_for_idle()
    result = await store.get(run.run_id)

    assert result is not None
    assert result.state is RunState.FAILED
    assert result.analysis is not None
    assert result.analysis.publication_eligible is False
    assert [item.code for item in result.analysis.approval_blockers] == [
        "LIVE_EVIDENCE_REQUIRED"
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "new_field", "expected_type"),
    [
        ("cust_email", "primary_email", "TEXT"),
        ("order_total", "preferred_order_total", "FLOAT"),
        ("order_status", "preferred_order_status", "NUMBER"),
    ],
)
async def test_replay_analysis_binds_each_selected_field_to_its_own_evidence(
    tmp_path: Path,
    field: str,
    new_field: str,
    expected_type: str,
) -> None:
    """A replay run must not fall back to the default email context."""
    store = RunStore(tmp_path / f"{field}.db")
    await store.initialize()
    orchestrator = ChangeSafeOrchestrator(
        store=store,
        context_port=ReplayDataHubContext.from_default(),
        generator=ArtifactGenerationService(),
    )
    change = golden_change().model_copy(
        update={
            "field": field,
            "new_field": new_field,
            "source_commit": f"multi-field-{field}",
        }
    )
    run = await store.create(change)

    result = await orchestrator.analyze(run.run_id)

    assert result.state is RunState.AWAITING_APPROVAL
    assert result.analysis is not None
    assert result.analysis.context.field == change.field
    assert result.analysis.context.field_type == expected_type
    assert result.analysis.publication_eligible is True
    assert result.analysis.validation.passed is True
    assert all(
        check.passed
        for check in result.analysis.validation.checks
        if check.blocking
    )
    model = result.analysis.artifacts.files[
        "models/marts/order_details__changesafe.sql"
    ].content
    assert change.field in model
    assert result.analysis.artifacts.manifest_hash is not None

    context = result.analysis.context
    saved_urns = {
        context.target_urn,
        *context.field_tags,
        *context.glossary_terms,
        *context.queries,
        *(item.urn for item in context.evidence),
        *(item.urn for item in context.upstream_assets),
        *(item.urn for item in context.downstream_assets),
    }
    for factor in result.analysis.risk.factors:
        assert set(factor.evidence_urns) <= saved_urns

    if field == "cust_email":
        return

    field_scoped = {
        "field_tags": context.field_tags,
        "glossary_terms": context.glossary_terms,
        "queries": context.queries,
        "evidence": [item.model_dump(mode="json") for item in context.evidence],
        "upstream_assets": [
            item.model_dump(mode="json") for item in context.upstream_assets
        ],
        "downstream_assets": [
            item.model_dump(mode="json") for item in context.downstream_assets
        ],
    }
    assert "cust_email" not in json.dumps(field_scoped).casefold()


@pytest.mark.asyncio
async def test_context_contract_failure_persists_safe_public_error(
    tmp_path: Path,
) -> None:
    store = RunStore(tmp_path / "runs.db")
    await store.initialize()
    orchestrator = ChangeSafeOrchestrator(
        store=store,
        context_port=ReplayDataHubContext.from_default(),
        generator=ArtifactGenerationService(),
    )
    incompatible = golden_change().model_copy(update={"field": "missing_field"})
    run = await store.create(incompatible)

    result = await orchestrator.analyze(run.run_id)

    assert result.state is RunState.FAILED
    assert result.error is not None
    assert result.error.code == "CONTEXT_LOAD_FAILED"
    assert "snapshot" not in result.error.message.lower()


@pytest.mark.asyncio
async def test_wait_for_idle_drains_background_analysis_before_shutdown(
    tmp_path: Path,
) -> None:
    store = RunStore(tmp_path / "runs.db")
    orchestrator = ChangeSafeOrchestrator(
        store=store,
        context_port=ReplayDataHubContext.from_default(),
        generator=ArtifactGenerationService(),
    )

    run = await orchestrator.start(golden_change())
    await orchestrator.wait_for_idle()

    completed = await store.get(run.run_id)
    assert completed is not None
    assert completed.state is RunState.AWAITING_APPROVAL
