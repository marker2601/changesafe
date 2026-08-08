from pathlib import Path

from changesafe.context.base import DataHubContextPort
from changesafe.context.replay import ReplayDataHubContext
from changesafe.domain import ChangeOperation, ChangeRequest, RunView
from changesafe.generation.service import ArtifactGenerationService
from changesafe.orchestrator import ChangeSafeOrchestrator
from changesafe.store import RunStore

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
