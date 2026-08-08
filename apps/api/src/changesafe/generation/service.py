"""Select optional narrative planning and always enforce reviewed templates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from changesafe.domain import (
    ArtifactBundle,
    ChangeRequest,
    ContextBundle,
    LlmUsage,
    RiskResult,
)
from changesafe.generation.openai_generator import (
    GenerationPlanningError,
    PlanningResult,
)
from changesafe.generation.templates import generate_artifacts


class PlannerPort(Protocol):
    async def plan(
        self, change: ChangeRequest, context: ContextBundle, risk: RiskResult
    ) -> PlanningResult: ...


@dataclass(frozen=True)
class GenerationResult:
    artifacts: ArtifactBundle
    usage: LlmUsage | None
    release_reservation: bool = False


class ArtifactGenerationService:
    def __init__(self, planner: PlannerPort | None = None) -> None:
        self.planner = planner

    async def generate(
        self, change: ChangeRequest, context: ContextBundle, risk: RiskResult
    ) -> ArtifactBundle:
        return (await self.generate_with_usage(change, context, risk)).artifacts

    async def generate_with_usage(
        self, change: ChangeRequest, context: ContextBundle, risk: RiskResult
    ) -> GenerationResult:
        narrative = None
        usage = None
        release_reservation = False
        if self.planner is not None:
            try:
                planned = await self.planner.plan(change, context, risk)
                narrative = planned.narrative
                usage = planned.usage
            except GenerationPlanningError as exc:
                usage = exc.usage if exc.usage_complete else None
                release_reservation = exc.usage_complete and exc.usage is None
                narrative = None
            except TimeoutError:
                narrative = None
        return GenerationResult(
            artifacts=generate_artifacts(change, context, risk, narrative),
            usage=usage,
            release_reservation=release_reservation,
        )
