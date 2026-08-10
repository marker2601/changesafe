"""Typed domain contracts shared by ChangeSafe services and HTTP routes."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from changesafe.sql_types import canonical_sql_type, validate_snowflake_type

SQL_TYPE_PATTERN = (
    r"^[A-Za-z][A-Za-z0-9_ ]*(?:\(\s*\d+(?:\s*,\s*\d+)?\s*\))?$"
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ChangeOperation(StrEnum):
    RENAME = "rename"
    REMOVE = "remove"
    TYPE_CHANGE = "type_change"


class WarehouseValidationStatus(StrEnum):
    NOT_RUN = "not_run"
    PASSED = "passed"
    BLOCKED = "blocked"


class WarehouseValidationMode(StrEnum):
    NONE = "none"
    AGGREGATE = "aggregate"


class ContextMode(StrEnum):
    LIVE = "live"
    SNAPSHOT = "snapshot"


class LineagePrecision(StrEnum):
    EXACT_FIELD = "exact_field"
    ENDPOINT_FIELD = "endpoint_field"
    DATASET_LEVEL = "dataset_level"


class RiskBand(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ImpactCategory(StrEnum):
    DATA_INTEGRITY = "data_integrity"
    PRIVACY_COMPLIANCE = "privacy_compliance"
    OPERATIONAL_CONTINUITY = "operational_continuity"
    TRUST_DECISION_QUALITY = "trust_decision_quality"
    FINANCIAL_EXPOSURE = "financial_exposure"
    ORGANIZATIONAL_IMPACT = "organizational_impact"


class ImpactSeverity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFORMATIONAL = "informational"


class EvidenceConfidence(StrEnum):
    DIRECT = "direct"
    INFERRED = "inferred"
    UNAVAILABLE = "unavailable"


class RunState(StrEnum):
    CREATED = "created"
    LOADING_CONTEXT = "loading_context"
    CONTEXT_FALLBACK_REQUIRED = "context_fallback_required"
    SCORING_RISK = "scoring_risk"
    GENERATING = "generating"
    VALIDATING = "validating"
    VALIDATING_WAREHOUSE = "validating_warehouse"
    AWAITING_APPROVAL = "awaiting_approval"
    PREPARING_PREVIEW = "preparing_preview"
    PUBLISHING = "publishing"
    COMPLETED = "completed"
    FAILED = "failed"
    PUBLICATION_FAILED = "publication_failed"


class ChangeRequest(StrictModel):
    asset_urn: str = Field(min_length=8, pattern=r"^urn:li:")
    operation: ChangeOperation
    field: str = Field(
        min_length=1, max_length=128, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$"
    )
    new_field: str | None = Field(
        default=None, max_length=128, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$"
    )
    old_type: str | None = Field(default=None, pattern=SQL_TYPE_PATTERN)
    new_type: str | None = Field(default=None, pattern=SQL_TYPE_PATTERN)
    source_commit: str = Field(min_length=1, max_length=200)
    requested_by: str = Field(min_length=1, max_length=200)

    @field_validator("old_type", "new_type")
    @classmethod
    def validate_type_semantics(cls, value: str | None) -> str | None:
        if value is not None:
            validate_snowflake_type(value)
        return value

    @model_validator(mode="after")
    def validate_operation_fields(self) -> ChangeRequest:
        if self.operation is ChangeOperation.RENAME:
            if not self.new_field:
                raise ValueError("new_field is required for a rename")
            if self.new_field == self.field:
                raise ValueError("new_field must differ from field")
            if self.old_type is not None or self.new_type is not None:
                raise ValueError("type fields are only valid for a type change")
        elif self.operation is ChangeOperation.REMOVE:
            if any(
                value is not None
                for value in (self.new_field, self.old_type, self.new_type)
            ):
                raise ValueError("operation fields are only valid for their operation")
        elif self.operation is ChangeOperation.TYPE_CHANGE:
            if self.new_field is not None:
                raise ValueError("new_field is only valid for a rename")
            if not self.old_type:
                raise ValueError("old_type is required for a type change")
            if not self.new_type:
                raise ValueError("new_type is required for a type change")
            if canonical_sql_type(self.new_type) == canonical_sql_type(self.old_type):
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
    lineage_degree: int | None = Field(default=None, ge=1)
    lineage_path: list[str] = Field(default_factory=list)
    lineage_precision: LineagePrecision


class Owner(StrictModel):
    urn: str = Field(min_length=1)
    name: str = Field(min_length=1)
    ownership_type: str = Field(min_length=1)


class SchemaField(StrictModel):
    name: str = Field(min_length=1, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    data_type: str = Field(min_length=1)
    nullable: bool = True


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


class SchemaCatalog(StrictModel):
    target_urn: str = Field(min_length=8, pattern=r"^urn:li:")
    target_name: str = Field(min_length=1)
    schema_fields: list[SchemaField] = Field(min_length=1)
    provenance: ContextProvenance

    @model_validator(mode="after")
    def require_unique_fields(self) -> SchemaCatalog:
        names = [field.name.casefold() for field in self.schema_fields]
        if len(names) != len(set(names)):
            raise ValueError("schema_fields contains duplicate field names")
        return self


class ContextBundle(StrictModel):
    target_urn: str
    target_name: str
    target_domain: str | None = None
    field: str
    field_type: str
    schema_fields: list[SchemaField] = Field(default_factory=list)
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


class ImpactAssessment(StrictModel):
    category: ImpactCategory
    label: str = Field(min_length=1)
    severity: ImpactSeverity
    confidence: EvidenceConfidence
    summary: str = Field(min_length=1)
    qualifier: str | None = None
    basis: str = Field(min_length=1)
    evidence_urns: list[str] = Field(min_length=1)


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


class WarehouseCheck(StrictModel):
    code: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(min_length=1, max_length=120)
    passed: bool
    retryable: bool = False
    detail: str = Field(min_length=1, max_length=500)
    observed_count: int | None = Field(default=None, ge=0)


class WarehouseValidationResult(StrictModel):
    status: WarehouseValidationStatus
    mode: WarehouseValidationMode
    environment_label: str = Field(min_length=1, max_length=80)
    operation: ChangeOperation
    field: str = Field(min_length=1, max_length=128)
    relation_fingerprint: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    started_at: datetime | None = None
    completed_at: datetime | None = None
    rows_evaluated: int | None = Field(default=None, ge=0)
    populated_row_count: int | None = Field(default=None, ge=0)
    unsafe_row_count: int | None = Field(default=None, ge=0)
    query_ids: list[str] = Field(default_factory=list, max_length=8)
    elapsed_ms: int | None = Field(default=None, ge=0)
    checks: list[WarehouseCheck] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def status_matches_evidence(self) -> WarehouseValidationResult:
        if self.status is WarehouseValidationStatus.PASSED:
            if self.mode is not WarehouseValidationMode.AGGREGATE:
                raise ValueError("passed warehouse evidence must be aggregate")
            if not self.checks or any(not check.passed for check in self.checks):
                raise ValueError("passed warehouse evidence requires passed checks")
        if self.status is WarehouseValidationStatus.NOT_RUN and (
            self.started_at is not None or self.query_ids
        ):
            raise ValueError("not-run evidence cannot claim execution")
        return self


class ApprovalBlocker(StrictModel):
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")
    message: str = Field(min_length=1, max_length=500)
    retryable: bool = False


class LlmUsage(StrictModel):
    provider: Literal["openai"] = "openai"
    model: str = Field(min_length=1)
    request_count: int = Field(ge=1, le=2)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    estimated_cost_usd: Decimal = Field(ge=0)


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
    publication_mode: Literal["live", "preview"] | None = None
    github_required: bool = False
    datahub_required: bool = False
    github_repository: str | None = None
    github_base_branch: str | None = None
    datahub_server: str | None = None
    datahub_target_urn: str | None = None
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
    impacts: list[ImpactAssessment] = Field(default_factory=list)
    warehouse_validation: WarehouseValidationResult = Field(
        default_factory=lambda: WarehouseValidationResult(
            status=WarehouseValidationStatus.NOT_RUN,
            mode=WarehouseValidationMode.NONE,
            environment_label="not configured",
            operation=ChangeOperation.RENAME,
            field="unavailable",
            checks=[],
        )
    )
    approval_blockers: list[ApprovalBlocker] = Field(default_factory=list)


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


class ReviewActivity(StrictModel):
    run_id: UUID
    session_label: str = Field(pattern=r"^session-(?:[0-9a-f]{8}|unassigned)$")
    scenario: str = Field(min_length=1)
    state: RunState
    context_mode: ContextMode | None = None
    publication_mode: Literal["live", "preview"] | None = None
    created_at: datetime
    updated_at: datetime
