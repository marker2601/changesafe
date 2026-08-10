import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from changesafe.demo import golden_change as official_change
from changesafe.domain import (
    AnalysisResult,
    ApprovalBlocker,
    ArtifactBundle,
    ArtifactFile,
    ChangeOperation,
    ChangeRequest,
    ContextBundle,
    ContextMode,
    ContextProvenance,
    LlmUsage,
    RiskBand,
    RiskResult,
    RunState,
    ValidationCheck,
    ValidationReport,
    WarehouseCheck,
    WarehouseValidationMode,
    WarehouseValidationResult,
    WarehouseValidationStatus,
)
from changesafe.store import InvalidTransition, LlmBudgetExceeded, RunStore

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


def passed_warehouse_result() -> WarehouseValidationResult:
    now = datetime.now(UTC)
    return WarehouseValidationResult(
        status=WarehouseValidationStatus.PASSED,
        mode=WarehouseValidationMode.AGGREGATE,
        environment_label="competition-non-production",
        operation=ChangeOperation.RENAME,
        field="customer_email",
        aggregate_query_started=True,
        binding_fingerprint="a" * 64,
        started_at=now - timedelta(seconds=1),
        completed_at=now,
        rows_evaluated=20,
        populated_row_count=20,
        query_ids=["safe-query-id"],
        elapsed_ms=1000,
        checks=[
            WarehouseCheck(
                code=code,
                label="No unsafe rows",
                passed=True,
                detail="No rows would lose a populated value.",
            )
            for code in (
                "warehouse_identity",
                "warehouse_schema",
                "rename_projection",
            )
        ],
    )


def analysis_result() -> AnalysisResult:
    return AnalysisResult(
        context=ContextBundle(
            target_urn=TARGET,
            target_name="dim_customers",
            field="customer_email",
            field_type="STRING",
            provenance=ContextProvenance(
                mode=ContextMode.LIVE,
                retrieved_at="2026-08-09T12:00:00Z",
                adapter_version="test",
            ),
        ),
        risk=RiskResult(
            score=0,
            band=RiskBand.LOW,
            factors=[],
            recommended_strategy="Proceed",
        ),
        artifacts=ArtifactBundle(
            files={
                "migration.sql": ArtifactFile(
                    path="migration.sql", content="SELECT 1"
                )
            }
        ),
        validation=ValidationReport(
            passed=True,
            checks=[
                ValidationCheck(
                    code="safe",
                    label="Safe",
                    passed=True,
                    detail="Safe artifact.",
                )
            ],
        ),
        publication_eligible=True,
        warehouse_validation=passed_warehouse_result(),
        approval_blockers=[
            ApprovalBlocker(
                code="WAREHOUSE_EVIDENCE_REVIEW",
                message="A reviewer must inspect the aggregate evidence.",
            )
        ],
    )


async def advance_to_awaiting_approval(
    store: RunStore, run_id: object, analysis: AnalysisResult
) -> None:
    for state in (
        RunState.LOADING_CONTEXT,
        RunState.SCORING_RISK,
        RunState.GENERATING,
        RunState.VALIDATING,
        RunState.VALIDATING_WAREHOUSE,
    ):
        await store.transition(run_id, state)
    await store.transition(run_id, RunState.AWAITING_APPROVAL, analysis=analysis)


@pytest.mark.asyncio
async def test_run_store_persists_uuid7_state_and_ordered_events(
    tmp_path: Path,
) -> None:
    database = tmp_path / "runs.db"
    store = RunStore(database)
    await store.initialize()

    created = await store.create(golden_change())
    loading = await store.transition(
        created.run_id,
        RunState.LOADING_CONTEXT,
        public_message="Loading DataHub context",
    )
    reopened = RunStore(database)
    persisted = await reopened.get(created.run_id)
    events = await reopened.events(created.run_id)

    assert created.run_id.version == 7
    assert loading.state is RunState.LOADING_CONTEXT
    assert persisted is not None
    assert persisted.state is RunState.LOADING_CONTEXT
    assert [event.sequence for event in events] == [1, 2]
    assert [event.state for event in events] == [
        RunState.CREATED,
        RunState.LOADING_CONTEXT,
    ]


@pytest.mark.asyncio
async def test_invalid_transition_is_rejected_without_new_event(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.db")
    await store.initialize()
    created = await store.create(golden_change())

    with pytest.raises(InvalidTransition, match=r"created.*completed"):
        await store.transition(created.run_id, RunState.COMPLETED)

    assert len(await store.events(created.run_id)) == 1


@pytest.mark.asyncio
async def test_event_resume_returns_only_sequences_after_cursor(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.db")
    await store.initialize()
    created = await store.create(golden_change())
    await store.transition(created.run_id, RunState.LOADING_CONTEXT)
    await store.transition(created.run_id, RunState.SCORING_RISK)

    resumed = await store.events(created.run_id, after_sequence=1)

    assert [event.sequence for event in resumed] == [2, 3]


@pytest.mark.asyncio
async def test_llm_budget_reservation_is_atomic_and_actual_usage_is_persisted(
    tmp_path: Path,
) -> None:
    store = RunStore(tmp_path / "runs.db")
    first = await store.create(
        golden_change(),
        llm_reservation_usd=Decimal("3"),
        llm_budget_usd=Decimal("5"),
    )

    with pytest.raises(LlmBudgetExceeded):
        await store.create(
            golden_change(),
            llm_reservation_usd=Decimal("3"),
            llm_budget_usd=Decimal("5"),
        )

    usage = LlmUsage(
        model="bounded-test-model",
        request_count=1,
        input_tokens=120,
        output_tokens=90,
        total_tokens=210,
        estimated_cost_usd=Decimal("1.25"),
    )
    await store.record_llm_usage(first.run_id, usage)
    second = await store.create(
        golden_change(),
        llm_reservation_usd=Decimal("3"),
        llm_budget_usd=Decimal("5"),
    )

    assert await store.get_llm_usage(first.run_id) == usage
    assert await store.get_llm_usage(second.run_id) is None
    assert await store.llm_committed_cost_usd() == Decimal("4.25")


@pytest.mark.asyncio
async def test_recent_activity_contains_only_operational_demo_fields(
    tmp_path: Path,
) -> None:
    store = RunStore(tmp_path / "runs.db")
    run = await store.create(
        official_change(), session_id="judge_session_0123456789"
    )

    activity = await store.recent_activity(limit=10)

    assert activity[0].run_id == run.run_id
    assert activity[0].session_label.startswith("session-")
    assert activity[0].scenario == "Order Entry Analytics"
    serialized = activity[0].model_dump_json()
    assert "cust_email" not in serialized
    assert "requested_by" not in serialized
    assert "judge_session_0123456789" not in serialized
    assert "judge" not in serialized.casefold()


@pytest.mark.asyncio
async def test_initialize_adds_session_id_to_an_existing_database(
    tmp_path: Path,
) -> None:
    import aiosqlite

    database = tmp_path / "legacy.db"
    async with aiosqlite.connect(database) as connection:
        await connection.execute(
            """CREATE TABLE runs (
                run_id TEXT PRIMARY KEY,
                state TEXT NOT NULL,
                request_json TEXT NOT NULL,
                analysis_json TEXT,
                publication_json TEXT,
                error_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )"""
        )
        await connection.commit()

    store = RunStore(database)
    await store.initialize()
    await store.create(official_change(), session_id="judge_session_0123456789")

    async with aiosqlite.connect(database) as connection:
        cursor = await connection.execute("PRAGMA table_info(runs)")
        columns = {str(row[1]) for row in await cursor.fetchall()}
    assert "session_id" in columns


@pytest.mark.asyncio
async def test_store_round_trips_warehouse_result_and_blockers(
    tmp_path: Path,
) -> None:
    store = RunStore(tmp_path / "runs.db")
    run = await store.create(golden_change())
    analysis = analysis_result()

    await advance_to_awaiting_approval(store, run.run_id, analysis)
    restored = await store.get(run.run_id)

    assert restored is not None
    assert restored.analysis == analysis
    assert restored.analysis.warehouse_validation.aggregate_query_started is True
    assert restored.analysis.approval_blockers == [
        ApprovalBlocker(
            code="WAREHOUSE_EVIDENCE_REVIEW",
            message="A reviewer must inspect the aggregate evidence.",
        )
    ]


@pytest.mark.asyncio
async def test_store_restores_pre_upgrade_analysis_with_warehouse_defaults(
    tmp_path: Path,
) -> None:
    import aiosqlite

    database = tmp_path / "runs.db"
    store = RunStore(database)
    run = await store.create(golden_change())
    analysis = analysis_result()
    await advance_to_awaiting_approval(store, run.run_id, analysis)
    legacy_analysis = analysis.model_dump(mode="json")
    legacy_analysis.pop("warehouse_validation")
    legacy_analysis.pop("approval_blockers")

    async with aiosqlite.connect(database) as connection:
        await connection.execute(
            "UPDATE runs SET analysis_json = ? WHERE run_id = ?",
            (json.dumps(legacy_analysis), str(run.run_id)),
        )
        await connection.commit()

    restored = await RunStore(database).get(run.run_id)

    assert restored is not None
    assert restored.analysis is not None
    assert restored.analysis.warehouse_validation.status is (
        WarehouseValidationStatus.NOT_RUN
    )
    assert restored.analysis.approval_blockers == []


@pytest.mark.asyncio
async def test_initialize_scrubs_legacy_query_text_from_models_and_sqlite_bytes(
    tmp_path: Path,
) -> None:
    import aiosqlite

    sentinel = "SENSITIVE_QUERY_TEXT_SENTINEL"
    database = tmp_path / "runs.db"
    store = RunStore(database)
    run = await store.create(golden_change())
    analysis = analysis_result()
    await advance_to_awaiting_approval(store, run.run_id, analysis)
    legacy_analysis = analysis.model_dump(mode="json")
    legacy_analysis["context"]["queries"] = [sentinel]

    async with aiosqlite.connect(database) as connection:
        await connection.execute(
            "UPDATE runs SET analysis_json = ? WHERE run_id = ?",
            (json.dumps(legacy_analysis), str(run.run_id)),
        )
        await connection.commit()
    assert sentinel.encode() in database.read_bytes()

    reopened = RunStore(database)
    await reopened.initialize()
    restored = await reopened.get(run.run_id)

    assert restored is not None
    assert restored.analysis is None
    sqlite_bytes = b"".join(
        path.read_bytes()
        for path in database.parent.glob(f"{database.name}*")
        if path.is_file()
    )
    assert sentinel.encode() not in sqlite_bytes


@pytest.mark.asyncio
async def test_store_restores_legacy_warehouse_result_with_unknown_query_boundary(
    tmp_path: Path,
) -> None:
    import aiosqlite

    database = tmp_path / "runs.db"
    store = RunStore(database)
    run = await store.create(golden_change())
    analysis = analysis_result()
    await advance_to_awaiting_approval(store, run.run_id, analysis)
    legacy_analysis = analysis.model_copy(
        update={"approval_blockers": [], "publication_eligible": True}
    ).model_dump(mode="json")
    legacy_analysis["warehouse_validation"].pop("aggregate_query_started")

    async with aiosqlite.connect(database) as connection:
        await connection.execute(
            "UPDATE runs SET analysis_json = ? WHERE run_id = ?",
            (json.dumps(legacy_analysis), str(run.run_id)),
        )
        await connection.commit()

    restored = await RunStore(database).get(run.run_id)

    assert restored is not None
    assert restored.analysis is not None
    assert restored.analysis.warehouse_validation.aggregate_query_started is None
    assert restored.analysis.publication_eligible is False
    assert restored.analysis.approval_blockers == [
        ApprovalBlocker(
            code="WAREHOUSE_EVIDENCE_INCOMPLETE",
            message="Warehouse validation evidence is incomplete.",
            retryable=False,
        )
    ]


@pytest.mark.asyncio
async def test_warehouse_transition_requires_validation_and_persists_events(
    tmp_path: Path,
) -> None:
    database = tmp_path / "runs.db"
    store = RunStore(database)
    run = await store.create(golden_change())

    with pytest.raises(
        InvalidTransition, match=r"loading_context.*validating_warehouse"
    ):
        await store.transition(run.run_id, RunState.LOADING_CONTEXT)
        await store.transition(run.run_id, RunState.VALIDATING_WAREHOUSE)

    await store.transition(run.run_id, RunState.SCORING_RISK)
    await store.transition(run.run_id, RunState.GENERATING)
    await store.transition(run.run_id, RunState.VALIDATING)
    await store.transition(run.run_id, RunState.VALIDATING_WAREHOUSE)
    reopened = RunStore(database)

    assert [event.state for event in await reopened.events(run.run_id)] == [
        RunState.CREATED,
        RunState.LOADING_CONTEXT,
        RunState.SCORING_RISK,
        RunState.GENERATING,
        RunState.VALIDATING,
        RunState.VALIDATING_WAREHOUSE,
    ]
