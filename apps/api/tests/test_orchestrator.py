from pathlib import Path

import pytest

from changesafe.context.replay import ReplayDataHubContext
from changesafe.demo import golden_change
from changesafe.domain import ImpactCategory, RunState
from changesafe.generation.service import ArtifactGenerationService
from changesafe.orchestrator import ChangeSafeOrchestrator
from changesafe.store import RunStore


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
    assert result.analysis.risk.score == 80
    assert result.analysis.validation.passed is True
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
