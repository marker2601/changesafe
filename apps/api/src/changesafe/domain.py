"""Typed domain contracts shared by ChangeSafe services and HTTP routes."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ChangeOperation(StrEnum):
    RENAME = "rename"
    REMOVE = "remove"
    TYPE_CHANGE = "type_change"


class ContextMode(StrEnum):
    LIVE = "live"
    SNAPSHOT = "snapshot"


class RiskBand(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RunState(StrEnum):
    CREATED = "created"
    LOADING_CONTEXT = "loading_context"
    SCORING_RISK = "scoring_risk"
    GENERATING = "generating"
    VALIDATING = "validating"
    AWAITING_APPROVAL = "awaiting_approval"
    PREPARING_PREVIEW = "preparing_preview"
    PUBLISHING = "publishing"
    COMPLETED = "completed"
    FAILED = "failed"
    PUBLICATION_FAILED = "publication_failed"


class ChangeRequest(StrictModel):
    asset_urn: str = Field(min_length=8, pattern=r"^urn:li:")
    operation: ChangeOperation
    field: str = Field(min_length=1, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    new_field: str | None = Field(default=None, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    old_type: str | None = None
    new_type: str | None = None
    source_commit: str = Field(min_length=1, max_length=200)
    requested_by: str = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def validate_operation_fields(self) -> ChangeRequest:
        if self.operation is ChangeOperation.RENAME:
            if not self.new_field:
                raise ValueError("new_field is required for a rename")
            if self.new_field == self.field:
                raise ValueError("new_field must differ from field")
        elif self.operation is ChangeOperation.TYPE_CHANGE:
            if not self.new_type:
                raise ValueError("new_type is required for a type change")
            if self.old_type and self.new_type.upper() == self.old_type.upper():
                raise ValueError("new_type must differ from old_type")
        return self


class EvidenceRef(StrictModel):
    urn: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    label: str = Field(min_length=1)
    path: list[str] = Field(default_factory=list)


class AffectedAsset(StrictModel):
    urn: str = Field(min_length=1)
    name: str = Field(min_length=1)
    entity_type: str = Field(min_length=1)
    domain: str | None = None
    field: str | None = None
    is_executive: bool = False
    is_production_ml: bool = False
    lineage_path: list[str] = Field(default_factory=list)


class Owner(StrictModel):
    urn: str = Field(min_length=1)
    name: str = Field(min_length=1)
    ownership_type: str = Field(min_length=1)


class ToolEvidence(StrictModel):
    tool: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    duration_ms: int = Field(ge=0)
    result_count: int = Field(ge=0)
    referenced_urns: list[str] = Field(default_factory=list)


class ContextProvenance(StrictModel):
    mode: ContextMode
    retrieved_at: datetime
    adapter_version: str
    snapshot_hash: str | None = None


class ContextBundle(StrictModel):
    target_urn: str
    target_name: str
    target_domain: str | None = None
    field: str
    field_type: str
    upstream_assets: list[AffectedAsset] = Field(default_factory=list)
    downstream_assets: list[AffectedAsset] = Field(default_factory=list)
    owners: list[Owner] = Field(default_factory=list)
    field_tags: list[str] = Field(default_factory=list)
    glossary_terms: list[str] = Field(default_factory=list)
    structured_properties: dict[str, list[str | int | float]] = Field(
        default_factory=dict
    )
    usage_tier: Literal["none", "low", "medium", "high"] = "none"
    queries: list[str] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    tool_evidence: list[ToolEvidence] = Field(default_factory=list)
    provenance: ContextProvenance

    @model_validator(mode="after")
    def require_snapshot_hash(self) -> ContextBundle:
        if (
            self.provenance.mode is ContextMode.SNAPSHOT
            and not self.provenance.snapshot_hash
        ):
            raise ValueError("snapshot_hash is required in snapshot mode")
        return self


class RiskFactor(StrictModel):
    code: str
    label: str
    points: int = Field(ge=0, le=100)
    evidence_urns: list[str] = Field(min_length=1)


class RiskResult(StrictModel):
    score: int = Field(ge=0, le=100)
    band: RiskBand
    factors: list[RiskFactor]
    recommended_strategy: str


class ArtifactFile(StrictModel):
    path: str
    content: str
    sha256: str = ""

    @model_validator(mode="after")
    def fill_hash(self) -> ArtifactFile:
        digest = sha256(self.content.encode("utf-8")).hexdigest()
        if self.sha256 and self.sha256 != digest:
            raise ValueError(f"sha256 does not match bytes for {self.path}")
        self.sha256 = digest
        return self


class ArtifactBundle(StrictModel):
    files: dict[str, ArtifactFile]
    manifest_hash: str | None = None


class ValidationCheck(StrictModel):
    code: str
    label: str
    passed: bool
    blocking: bool = True
    detail: str


class ValidationReport(StrictModel):
    passed: bool
    checks: list[ValidationCheck]

    def check(self, code: str) -> ValidationCheck:
        return next(item for item in self.checks if item.code == code)


class DataHubReceipt(StrictModel):
    mode: Literal["live", "preview"]
    label: str
    document_urn: str | None = None
    updated_urns: list[str] = Field(default_factory=list)
    mutations: list[str] = Field(default_factory=list)
    idempotent_reuse: bool = False


class PublicationReceipt(StrictModel):
    mode: Literal["live", "preview"]
    idempotency_key: str
    artifact_hash: str
    branch: str | None = None
    pull_request_url: str | None = None
    patch: str | None = None
    writeback: DataHubReceipt


class PublicationLedgerEntry(StrictModel):
    idempotency_key: str = Field(min_length=64, max_length=64)
    run_id: UUID
    artifact_hash: str = Field(min_length=64, max_length=64)
    approved_at: datetime
    branch: str | None = None
    pull_request_url: str | None = None
    writeback: DataHubReceipt | None = None
    receipt: PublicationReceipt | None = None
    completed: bool = False
    created_at: datetime
    updated_at: datetime


class AnalysisResult(StrictModel):
    context: ContextBundle
    risk: RiskResult
    artifacts: ArtifactBundle
    validation: ValidationReport
    publication_eligible: bool


class PublicError(StrictModel):
    code: str
    message: str
    retryable: bool = False


class RunView(StrictModel):
    run_id: UUID
    state: RunState
    request: ChangeRequest
    analysis: AnalysisResult | None = None
    publication: PublicationReceipt | None = None
    error: PublicError | None = None
    created_at: datetime
    updated_at: datetime


class RunEvent(StrictModel):
    run_id: UUID
    sequence: int = Field(ge=1)
    state: RunState
    public_message: str
    evidence: list[EvidenceRef] = Field(default_factory=list)
    created_at: datetime
