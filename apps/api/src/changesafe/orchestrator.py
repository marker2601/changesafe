"""Run the fail-closed metadata-aware change analysis workflow."""

from __future__ import annotations

import asyncio
from decimal import Decimal
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
from changesafe.impact import classify_impacts
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
        snapshot_context_port: DataHubContextPort | None = None,
        llm_reservation_usd: Decimal = Decimal(0),
        llm_budget_usd: Decimal | None = None,
    ) -> None:
        self.store = store
        self.context_port = context_port
        self.generator = generator
        self.snapshot_context_port = snapshot_context_port
        self.llm_reservation_usd = llm_reservation_usd
        self.llm_budget_usd = llm_budget_usd
        self._tasks: set[asyncio.Task[RunView]] = set()
        self._fallback_lock = asyncio.Lock()

    def _track(self, task: asyncio.Task[RunView]) -> None:
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def start(
        self, change: ChangeRequest, *, session_id: str | None = None
    ) -> RunView:
        run = await self.store.create(
            change,
            session_id=session_id,
            llm_reservation_usd=self.llm_reservation_usd,
            llm_budget_usd=self.llm_budget_usd,
        )
        task = asyncio.create_task(self.analyze(run.run_id))
        self._track(task)
        return run

    async def analyze(self, run_id: UUID | str) -> RunView:
        run = await self.store.get(run_id)
        if run is None:
            raise KeyError(str(run_id))

        await self.store.transition(
            run_id,
            RunState.LOADING_CONTEXT,
            public_message="Reading the existing data contract",
        )
        return await self._analyze_from_loading(
            run,
            self.context_port,
            offer_snapshot=self.snapshot_context_port is not None,
        )

    async def continue_with_snapshot(self, run_id: UUID | str) -> RunView:
        if self.snapshot_context_port is None:
            raise ValueError("Snapshot fallback is not configured.")
        async with self._fallback_lock:
            run = await self.store.get(run_id)
            if run is None:
                raise KeyError(str(run_id))
            if run.state is not RunState.CONTEXT_FALLBACK_REQUIRED:
                raise ValueError(
                    "Run is not waiting for snapshot fallback confirmation."
                )
            loading = await self.store.transition(
                run_id,
                RunState.LOADING_CONTEXT,
                public_message="Loading confirmed DataHub snapshot",
                clear_error=True,
            )
            task = asyncio.create_task(
                self._analyze_from_loading(
                    loading,
                    self.snapshot_context_port,
                    offer_snapshot=False,
                )
            )
            self._track(task)
            return loading

    async def _analyze_from_loading(
        self,
        run: RunView,
        context_port: DataHubContextPort,
        *,
        offer_snapshot: bool,
    ) -> RunView:
        try:
            context = await context_port.load(run.request)
            await self.store.transition(
                run.run_id,
                RunState.SCORING_RISK,
                public_message="Classifying business and technical impact",
                evidence=context.evidence,
            )
            risk = score_change(run.request, context)
            impacts = classify_impacts(run.request, context)
            await self.store.transition(
                run.run_id,
                RunState.GENERATING,
                public_message="Preparing a compatible migration",
            )
            generation = await self.generator.generate_with_usage(
                run.request, context, risk
            )
            if generation.usage is not None:
                await self.store.record_llm_usage(run.run_id, generation.usage)
            elif generation.release_reservation:
                await self.store.release_llm_reservation(run.run_id)
            artifacts = generation.artifacts
            await self.store.transition(
                run.run_id,
                RunState.VALIDATING,
                public_message="Proving the generated change is safe",
            )
            validation = verify_artifacts(artifacts, run.request, context)
            analysis = AnalysisResult(
                context=context,
                risk=risk,
                artifacts=artifacts,
                validation=validation,
                publication_eligible=validation.passed,
                impacts=impacts,
            )
            if not validation.passed:
                return await self.store.transition(
                    run.run_id,
                    RunState.FAILED,
                    public_message="Artifact validation failed",
                    analysis=analysis,
                    error=PublicError(
                        code="VERIFICATION_FAILED",
                        message="Generated artifacts did not pass safety checks.",
                    ),
                )
            return await self.store.transition(
                run.run_id,
                RunState.AWAITING_APPROVAL,
                public_message="Waiting for the accountable owner",
                analysis=analysis,
            )
        except ContextLoadError:
            if offer_snapshot:
                return await self.store.transition(
                    run.run_id,
                    RunState.CONTEXT_FALLBACK_REQUIRED,
                    public_message="Live context unavailable; confirmation required",
                    error=PublicError(
                        code="LIVE_CONTEXT_UNAVAILABLE",
                        message=(
                            "Live metadata context is unavailable. Snapshot replay "
                            "requires confirmation."
                        ),
                        retryable=True,
                    ),
                )
            return await self.store.transition(
                run.run_id,
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
                run.run_id,
                RunState.FAILED,
                public_message="Analysis failed safely",
                error=PublicError(
                    code="ANALYSIS_FAILED",
                    message="The change analysis could not be completed.",
                    retryable=True,
                ),
            )
