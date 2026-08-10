export type ChangeOperation = "rename" | "remove" | "type_change";
export type RunState =
  | "created"
  | "loading_context"
  | "context_fallback_required"
  | "scoring_risk"
  | "generating"
  | "validating"
  | "validating_warehouse"
  | "awaiting_approval"
  | "preparing_preview"
  | "publishing"
  | "completed"
  | "failed"
  | "publication_failed";

export interface ChangeRequest {
  asset_urn: string;
  operation: ChangeOperation;
  field: string;
  new_field: string | null;
  old_type: string | null;
  new_type: string | null;
  source_commit: string;
  requested_by: string;
}

export interface EvidenceRef {
  urn: string;
  kind: string;
  label: string;
  path: string[];
}

export interface AffectedAsset {
  urn: string;
  name: string;
  entity_type: string;
  domain: string | null;
  field: string | null;
  is_executive: boolean;
  is_production_ml: boolean;
  lineage_degree: number | null;
  lineage_path: string[];
  lineage_precision: "exact_field" | "endpoint_field" | "dataset_level";
}

export interface SchemaField {
  name: string;
  data_type: string;
  nullable: boolean;
}

export interface ContextBundle {
  target_urn: string;
  target_name: string;
  target_domain: string | null;
  field: string;
  field_type: string;
  schema_fields: SchemaField[];
  upstream_assets: AffectedAsset[];
  downstream_assets: AffectedAsset[];
  owners: Array<{ urn: string; name: string; ownership_type: string }>;
  field_tags: string[];
  glossary_terms: string[];
  structured_properties: Record<string, Array<string | number>>;
  usage_tier: "none" | "low" | "medium" | "high";
  query_count: number;
  evidence: EvidenceRef[];
  tool_evidence: Array<{
    tool: string;
    parameters: Record<string, unknown>;
    duration_ms: number;
    result_count: number;
    referenced_urns: string[];
  }>;
  provenance: {
    mode: "live" | "snapshot";
    retrieved_at: string;
    adapter_version: string;
    snapshot_hash: string | null;
  };
}

export interface SchemaCatalog {
  target_urn: string;
  target_name: string;
  schema_fields: SchemaField[];
  provenance: ContextBundle["provenance"];
}

export type SchemaEvidenceSource = "active" | "recorded";

export interface RiskFactor {
  code: string;
  label: string;
  points: number;
  evidence_urns: string[];
}

export interface RiskResult {
  score: number;
  band: "low" | "medium" | "high" | "critical";
  factors: RiskFactor[];
  recommended_strategy: string;
}

export type ImpactCategory =
  | "data_integrity"
  | "privacy_compliance"
  | "operational_continuity"
  | "trust_decision_quality"
  | "financial_exposure"
  | "organizational_impact";

export type ImpactSeverity =
  | "critical"
  | "high"
  | "medium"
  | "low"
  | "informational";

export type EvidenceConfidence = "direct" | "inferred" | "unavailable";

export interface ImpactAssessment {
  category: ImpactCategory;
  label: string;
  severity: ImpactSeverity;
  confidence: EvidenceConfidence;
  summary: string;
  qualifier: string | null;
  basis: string;
  evidence_urns: string[];
}

export interface ArtifactFile {
  path: string;
  content: string;
  sha256: string;
}

export interface ArtifactBundle {
  files: Record<string, ArtifactFile>;
  manifest_hash: string | null;
}

export interface ValidationCheck {
  code: string;
  label: string;
  passed: boolean;
  blocking: boolean;
  detail: string;
}

export interface ValidationReport {
  passed: boolean;
  checks: ValidationCheck[];
}

export type WarehouseValidationStatus = "not_run" | "passed" | "blocked";
export type WarehouseValidationMode = "none" | "aggregate";

export interface WarehouseCheck {
  code: string;
  label: string;
  passed: boolean;
  retryable: boolean;
  detail: string;
  observed_count: number | null;
}

export interface WarehouseValidationResult {
  status: WarehouseValidationStatus;
  mode: WarehouseValidationMode;
  environment_label: string;
  operation: ChangeOperation;
  field: string;
  aggregate_query_started: boolean | null;
  started_at: string | null;
  completed_at: string | null;
  rows_evaluated: number | null;
  populated_row_count: number | null;
  unsafe_row_count: number | null;
  query_ids: string[];
  elapsed_ms: number | null;
  checks: WarehouseCheck[];
}

export interface ApprovalBlocker {
  code: string;
  message: string;
  retryable: boolean;
}

export interface DataHubReceipt {
  mode: "live" | "preview";
  label: string;
  document_urn: string | null;
  updated_urns: string[];
  mutations: string[];
  idempotent_reuse: boolean;
}

export interface PublicationReceipt {
  mode: "live" | "preview";
  idempotency_key: string;
  artifact_hash: string;
  branch: string | null;
  pull_request_url: string | null;
  patch: string | null;
  writeback: DataHubReceipt;
}

export interface AnalysisResult {
  context: ContextBundle;
  risk: RiskResult;
  artifacts: ArtifactBundle;
  validation: ValidationReport;
  publication_eligible: boolean;
  impacts: ImpactAssessment[];
  warehouse_validation: WarehouseValidationResult;
  approval_blockers: ApprovalBlocker[];
}

export interface PublicError {
  code: string;
  message: string;
  retryable: boolean;
}

export interface RunView {
  run_id: string;
  state: RunState;
  request: ChangeRequest;
  analysis: AnalysisResult | null;
  publication: PublicationReceipt | null;
  error: PublicError | null;
  created_at: string;
  updated_at: string;
}

export interface RunEvent {
  run_id: string;
  sequence: number;
  state: RunState;
  public_message: string;
  evidence: EvidenceRef[];
  created_at: string;
}

export interface PublicConfig {
  mode: "replay" | "live" | "auto";
  live_context_available: boolean;
  datahub_ui_url: string | null;
  llm_available: boolean;
  github_publication_available: boolean;
  datahub_writeback_available: boolean;
  owner_activity_available: boolean;
  openai_model: string;
  live_evidence_required: boolean;
  warehouse_validation_available: boolean;
  warehouse_validation_required: boolean;
  warehouse_environment_label: string;
}

export interface ReviewActivity {
  run_id: string;
  session_label: string;
  scenario: string;
  state: RunState;
  context_mode: "live" | "snapshot" | null;
  publication_mode: "live" | "preview" | null;
  created_at: string;
  updated_at: string;
}

export type RunEventHandler = (event: RunEvent) => void;
export type SubscriptionErrorHandler = () => void;

export interface ChangeSafeApi {
  getPublicConfig(): Promise<PublicConfig>;
  getSchemaCatalog(
    assetUrn: string,
    source?: SchemaEvidenceSource,
  ): Promise<SchemaCatalog>;
  getOwnerActivity(adminToken: string): Promise<ReviewActivity[]>;
  createRun(change: ChangeRequest): Promise<RunView>;
  getRun(runId: string): Promise<RunView>;
  approve(runId: string, adminToken?: string): Promise<PublicationReceipt>;
  continueWithSnapshot(runId: string): Promise<RunView>;
  subscribe(
    runId: string,
    afterSequence: number,
    onEvent: RunEventHandler,
    onError?: SubscriptionErrorHandler,
  ): () => void;
  patchUrl?: (runId: string) => string;
}
