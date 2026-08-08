export type ChangeOperation = "rename" | "remove" | "type_change";
export type RunState =
  | "created"
  | "loading_context"
  | "scoring_risk"
  | "generating"
  | "validating"
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
  lineage_path: string[];
}

export interface ContextBundle {
  target_urn: string;
  target_name: string;
  target_domain: string | null;
  field: string;
  field_type: string;
  upstream_assets: AffectedAsset[];
  downstream_assets: AffectedAsset[];
  owners: Array<{ urn: string; name: string; ownership_type: string }>;
  field_tags: string[];
  glossary_terms: string[];
  structured_properties: Record<string, Array<string | number>>;
  usage_tier: "none" | "low" | "medium" | "high";
  queries: string[];
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
  llm_available: boolean;
  github_publication_available: boolean;
  datahub_writeback_available: boolean;
  openai_model: string;
}

export type RunEventHandler = (event: RunEvent) => void;
export type SubscriptionErrorHandler = () => void;

export interface ChangeSafeApi {
  getPublicConfig(): Promise<PublicConfig>;
  createRun(change: ChangeRequest): Promise<RunView>;
  getRun(runId: string): Promise<RunView>;
  approve(runId: string, adminToken?: string): Promise<PublicationReceipt>;
  subscribe(
    runId: string,
    afterSequence: number,
    onEvent: RunEventHandler,
    onError?: SubscriptionErrorHandler,
  ): () => void;
  patchUrl?: (runId: string) => string;
}
