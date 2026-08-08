from decimal import Decimal
from pathlib import Path

import pytest

from changesafe.domain import ChangeOperation, ChangeRequest, LlmUsage, RunState
from changesafe.store import InvalidTransition, LlmBudgetExceeded, RunStore

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
