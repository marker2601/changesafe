from pathlib import Path

from changesafe.context.base import DataHubContextPort
from changesafe.context.replay import ReplayDataHubContext
from changesafe.demo import golden_change
from changesafe.domain import RunView
from changesafe.generation.service import ArtifactGenerationService
from changesafe.orchestrator import ChangeSafeOrchestrator
from changesafe.store import RunStore

async def analyzed_run(
    tmp_path: Path,
    *,
    context_port: DataHubContextPort | None = None,
) -> tuple[RunStore, DataHubContextPort, RunView]:
    store = RunStore(tmp_path / "runs.db")
    context = context_port or ReplayDataHubContext.from_default()
    orchestrator = ChangeSafeOrchestrator(
        store=store,
        context_port=context,
        generator=ArtifactGenerationService(),
    )
    run = await store.create(golden_change())
    return store, context, await orchestrator.analyze(run.run_id)
