"""Run the fail-closed metadata-aware change analysis workflow."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Mapping
from contextlib import suppress
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from changesafe.context.base import ContextLoadError, DataHubContextPort
from changesafe.domain import (
    AnalysisResult,
    ChangeRequest,
    ContextBundle,
    PublicError,
    RunState,
    RunView,
    WarehouseCheck,
    WarehouseValidationMode,
    WarehouseValidationResult,
    WarehouseValidationStatus,
)
from changesafe.generation.service import ArtifactGenerationService
from changesafe.impact import classify_impacts
from changesafe.policy import evaluate_approval_policy
from changesafe.risk import score_change
from changesafe.store import RunStore
from changesafe.verification import verify_artifacts
from changesafe.warehouse.base import (
    WarehouseValidationError,
    WarehouseValidationPort,
)
from changesafe.warehouse.queries import fingerprint_relation

WAREHOUSE_CHECK_CODE = re.compile(r"^[a-z][a-z0-9_]*$")


class ChangeSafeOrchestrator:
    def __init__(
        self,
        *,
        store: RunStore,
        context_port: DataHubContextPort,
        generator: ArtifactGenerationService,
        snapshot_context_port: DataHubContextPort | None = None,
        warehouse_port: WarehouseValidationPort | None = None,
        require_live_evidence: bool = False,
        require_warehouse: bool = False,
        warehouse_max_age_seconds: int = 900,
        warehouse_timeout_seconds: float = 20,
        warehouse_environment_label: str = "not configured",
        warehouse_target_map: Mapping[str, str] | None = None,
        llm_reservation_usd: Decimal = Decimal(0),
        llm_budget_usd: Decimal | None = None,
    ) -> None:
        self.store = store
        self.context_port = context_port
        self.generator = generator
        self.snapshot_context_port = snapshot_context_port
        self.warehouse_port = warehouse_port
        self.require_live_evidence = require_live_evidence
        self.require_warehouse = require_warehouse
        self.warehouse_max_age_seconds = warehouse_max_age_seconds
        self.warehouse_timeout_seconds = warehouse_timeout_seconds
        self.warehouse_environment_label = warehouse_environment_label
        self.warehouse_target_map = dict(warehouse_target_map or {})
        self.llm_reservation_usd = llm_reservation_usd
        self.llm_budget_usd = llm_budget_usd
        self._tasks: set[asyncio.Task[RunView]] = set()
        self._warehouse_cleanup_tasks: set[
            asyncio.Task[WarehouseValidationResult]
        ] = set()
        self._fallback_lock = asyncio.Lock()

    def _track(self, task: asyncio.Task[RunView]) -> None:
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def _track_warehouse_cleanup(
        self, task: asyncio.Task[WarehouseValidationResult]
    ) -> None:
        self._warehouse_cleanup_tasks.add(task)
        task.add_done_callback(self._consume_warehouse_cleanup)

    def _consume_warehouse_cleanup(
        self, task: asyncio.Task[WarehouseValidationResult]
    ) -> None:
        self._warehouse_cleanup_tasks.discard(task)
        with suppress(asyncio.CancelledError):
            task.exception()

    async def wait_for_idle(self) -> None:
        """Wait for every in-flight background analysis to finish safely."""

        while self._tasks or self._warehouse_cleanup_tasks:
            await asyncio.gather(
                *tuple(self._tasks),
                *tuple(self._warehouse_cleanup_tasks),
                return_exceptions=True,
            )

    def _expected_relation_fingerprint(self, change: ChangeRequest) -> str | None:
        relation = self.warehouse_target_map.get(change.asset_urn)
        return fingerprint_relation(relation) if relation is not None else None

    def _not_run_result(self, change: ChangeRequest) -> WarehouseValidationResult:
        return WarehouseValidationResult(
            status=WarehouseValidationStatus.NOT_RUN,
            mode=WarehouseValidationMode.NONE,
            environment_label=self.warehouse_environment_label,
            operation=change.operation,
            field=change.field,
        )

    def _blocked_result(
        self,
        change: ChangeRequest,
        *,
        started_at: datetime,
        code: str,
        message: str,
        retryable: bool,
    ) -> WarehouseValidationResult:
        safe_code = code if WAREHOUSE_CHECK_CODE.fullmatch(code) else "warehouse_error"
        completed_at = datetime.now(UTC)
        return WarehouseValidationResult(
            status=WarehouseValidationStatus.BLOCKED,
            mode=WarehouseValidationMode.AGGREGATE,
            environment_label=self.warehouse_environment_label,
            operation=change.operation,
            field=change.field,
            relation_fingerprint=self._expected_relation_fingerprint(change),
            started_at=started_at,
            completed_at=completed_at,
            elapsed_ms=max(0, int((completed_at - started_at).total_seconds() * 1000)),
            checks=[
                WarehouseCheck(
                    code=safe_code,
                    label="Warehouse validation",
                    passed=False,
                    retryable=retryable,
                    detail=message,
                )
            ],
        )

    async def _validate_warehouse(
        self,
        change: ChangeRequest,
        context: ContextBundle,
    ) -> WarehouseValidationResult:
        assert self.warehouse_port is not None
        started_at = datetime.now(UTC)
        validation_task = asyncio.create_task(
            self.warehouse_port.validate(change, context)
        )
        try:
            done, _ = await asyncio.wait(
                {validation_task}, timeout=self.warehouse_timeout_seconds
            )
            if validation_task not in done:
                self._track_warehouse_cleanup(validation_task)
                validation_task.cancel()
                return self._blocked_result(
                    change,
                    started_at=started_at,
                    code="warehouse_timeout",
                    message="Warehouse validation timed out.",
                    retryable=True,
                )
            result = validation_task.result()
            validated = WarehouseValidationResult.model_validate(result)
            if validated.status is WarehouseValidationStatus.NOT_RUN:
                return self._blocked_result(
                    change,
                    started_at=started_at,
                    code="warehouse_not_run",
                    message="Warehouse validation returned no execution evidence.",
                    retryable=True,
                )
            return validated
        except WarehouseValidationError as exc:
            return self._blocked_result(
                change,
                started_at=started_at,
                code=exc.code,
                message=exc.public_message,
                retryable=exc.retryable,
            )
        except asyncio.CancelledError:
            self._track_warehouse_cleanup(validation_task)
            validation_task.cancel()
            raise
        except TimeoutError:
            return self._blocked_result(
                change,
                started_at=started_at,
                code="warehouse_timeout",
                message="Warehouse validation timed out.",
                retryable=True,
            )
        except Exception:
            return self._blocked_result(
                change,
                started_at=started_at,
                code="warehouse_error",
                message="Warehouse validation did not complete.",
                retryable=True,
            )

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
            warehouse = self._not_run_result(run.request)
            expected_relation_fingerprint = self._expected_relation_fingerprint(
                run.request
            )
            if validation.passed and self.warehouse_port is not None:
                await self.store.transition(
                    run.run_id,
                    RunState.VALIDATING_WAREHOUSE,
                    public_message="Validating aggregate warehouse evidence",
                )
                warehouse = await self._validate_warehouse(run.request, context)
            blockers = evaluate_approval_policy(
                change=run.request,
                context=context,
                validation=validation,
                warehouse=warehouse,
                require_live_evidence=self.require_live_evidence,
                require_warehouse=self.require_warehouse,
                warehouse_max_age_seconds=self.warehouse_max_age_seconds,
                expected_relation_fingerprint=expected_relation_fingerprint,
            )
            analysis = AnalysisResult(
                context=context,
                risk=risk,
                artifacts=artifacts,
                validation=validation,
                publication_eligible=validation.passed and not blockers,
                impacts=impacts,
                warehouse_validation=warehouse,
                approval_blockers=blockers,
            )
            if blockers:
                first_blocker = blockers[0]
                return await self.store.transition(
                    run.run_id,
                    RunState.FAILED,
                    public_message=(
                        "Artifact validation failed"
                        if first_blocker.code == "VERIFICATION_FAILED"
                        else "Approval policy blocked the analysis"
                    ),
                    analysis=analysis,
                    error=PublicError(
                        code=first_blocker.code,
                        message=first_blocker.message,
                        retryable=first_blocker.retryable,
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
