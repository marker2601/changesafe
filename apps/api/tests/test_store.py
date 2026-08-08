from pathlib import Path

import pytest

from changesafe.domain import ChangeOperation, ChangeRequest, RunState
from changesafe.store import InvalidTransition, RunStore

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
