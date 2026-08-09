from decimal import Decimal
from pathlib import Path

import pytest

from changesafe.demo import golden_change as official_change
from changesafe.domain import ChangeOperation, ChangeRequest, LlmUsage, RunState
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
