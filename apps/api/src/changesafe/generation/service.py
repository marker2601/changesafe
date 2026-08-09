"""Generate reviewed deterministic artifacts without planner-authored operations."""

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
from changesafe.generation.openai_generator import PlanningResult
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
        return GenerationResult(
            artifacts=generate_artifacts(change, context, risk),
            usage=None,
            release_reservation=False,
        )
