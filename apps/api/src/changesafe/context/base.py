"""Ports and shared inputs for DataHub reads and governed writeback."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any, Protocol

from pydantic import Field

from changesafe.domain import (
    ChangeRequest,
    ContextBundle,
    DataHubReceipt,
    EvidenceRef,
    RiskBand,
    RiskFactor,
    SchemaCatalog,
    StrictModel,
    ValidationCheck,
)


class ContextLoadError(RuntimeError):
    """A stable context acquisition failure safe for orchestration mapping."""


class ContextAuthorizationError(ContextLoadError):
    """DataHub rejected the configured credential; retries are unsafe/useless."""


class ContextTimeoutError(ContextLoadError):
    """DataHub did not complete a bounded tool call."""


class ContextTransportError(ContextLoadError):
    """DataHub could not be reached after the bounded retry policy."""


class DecisionWriteback(StrictModel):
    run_id: str = Field(min_length=8)
    change: ChangeRequest
    risk_score: int = Field(ge=0, le=100)
    risk_band: RiskBand
    artifact_hash: str = Field(min_length=64, max_length=64)
    approved_at: datetime
    pull_request_url: str | None = None
    idempotency_key: str = Field(min_length=64, max_length=64)
    risk_factors: list[RiskFactor] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    validation_checks: list[ValidationCheck] = Field(default_factory=list)
    migration_summary: str = ""
    rollback_summary: str = ""


WritebackProgress = Callable[[DataHubReceipt], Awaitable[None]]


class DataHubContextPort(Protocol):
    async def load(self, change: ChangeRequest) -> ContextBundle: ...

    async def discover_schema(self, asset_urn: str) -> SchemaCatalog: ...

    async def writeback(
        self,
        decision: DecisionWriteback,
        *,
        progress: DataHubReceipt | None = None,
        on_progress: WritebackProgress | None = None,
    ) -> DataHubReceipt: ...


class ToolRunner(Protocol):
    async def call(self, tool: str, **parameters: Any) -> Any: ...
