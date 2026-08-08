"""Run the fail-closed metadata-aware change analysis workflow."""

from __future__ import annotations

import asyncio
from uuid import UUID

from changesafe.context.base import ContextLoadError, DataHubContextPort
from changesafe.domain import (
    AnalysisResult,
    ChangeRequest,
    PublicError,
    RunState,
    RunView,
)
from changesafe.generation.service import ArtifactGenerationService
from changesafe.risk import score_change
from changesafe.store import RunStore
from changesafe.verification import verify_artifacts


class ChangeSafeOrchestrator:
    def __init__(
        self,
        *,
        store: RunStore,
        context_port: DataHubContextPort,
        generator: ArtifactGenerationService,
    ) -> None:
        self.store = store
        self.context_port = context_port
        self.generator = generator
        self._tasks: set[asyncio.Task[RunView]] = set()

    async def start(self, change: ChangeRequest) -> RunView:
        run = await self.store.create(change)
        task = asyncio.create_task(self.analyze(run.run_id))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return run

    async def analyze(self, run_id: UUID | str) -> RunView:
        run = await self.store.get(run_id)
        if run is None:
            raise KeyError(str(run_id))

        try:
            await self.store.transition(
                run_id,
                RunState.LOADING_CONTEXT,
                public_message="Loading DataHub context",
            )
            context = await self.context_port.load(run.request)
            await self.store.transition(
                run_id,
                RunState.SCORING_RISK,
                public_message="Scoring deterministic change risk",
                evidence=context.evidence,
            )
            risk = score_change(run.request, context)
            await self.store.transition(
                run_id,
                RunState.GENERATING,
                public_message="Generating migration artifacts",
            )
            artifacts = await self.generator.generate(run.request, context, risk)
            await self.store.transition(
                run_id,
                RunState.VALIDATING,
                public_message="Validating generated artifacts",
            )
            validation = verify_artifacts(artifacts, run.request, context)
            analysis = AnalysisResult(
                context=context,
                risk=risk,
                artifacts=artifacts,
                validation=validation,
                publication_eligible=validation.passed,
            )
            if not validation.passed:
                return await self.store.transition(
                    run_id,
                    RunState.FAILED,
                    public_message="Artifact validation failed",
                    analysis=analysis,
                    error=PublicError(
                        code="VERIFICATION_FAILED",
                        message="Generated artifacts did not pass safety checks.",
                    ),
                )
            return await self.store.transition(
                run_id,
                RunState.AWAITING_APPROVAL,
                public_message="Analysis complete; approval required",
                analysis=analysis,
            )
        except ContextLoadError:
            return await self.store.transition(
                run_id,
                RunState.FAILED,
                public_message="Metadata context could not be loaded",
                error=PublicError(
                    code="CONTEXT_LOAD_FAILED",
                    message="Unable to load metadata context.",
                    retryable=True,
                ),
            )
        except Exception:
            return await self.store.transition(
                run_id,
                RunState.FAILED,
                public_message="Analysis failed safely",
                error=PublicError(
                    code="ANALYSIS_FAILED",
                    message="The change analysis could not be completed.",
                    retryable=True,
                ),
            )
