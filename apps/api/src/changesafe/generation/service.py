"""Select optional narrative planning and always enforce reviewed templates."""

from __future__ import annotations

from typing import Protocol

from changesafe.domain import ArtifactBundle, ChangeRequest, ContextBundle, RiskResult
from changesafe.generation.openai_generator import GenerationPlanningError
from changesafe.generation.templates import GenerationNarrative, generate_artifacts


class PlannerPort(Protocol):
    async def plan(
        self, change: ChangeRequest, context: ContextBundle, risk: RiskResult
    ) -> GenerationNarrative: ...


class ArtifactGenerationService:
    def __init__(self, planner: PlannerPort | None = None) -> None:
        self.planner = planner

    async def generate(
        self, change: ChangeRequest, context: ContextBundle, risk: RiskResult
    ) -> ArtifactBundle:
        narrative = None
        if self.planner is not None:
            try:
                narrative = await self.planner.plan(change, context, risk)
            except (GenerationPlanningError, TimeoutError):
                narrative = None
        return generate_artifacts(change, context, risk, narrative)
