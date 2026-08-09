import { vi } from "vitest";

import type {
  AffectedAsset,
  ChangeSafeApi,
  ImpactAssessment,
  PublicConfig,
  PublicationReceipt,
  RunEvent,
  RunView,
} from "../src/types";

const NOW = "2026-08-08T20:00:00Z";
export const RUN_ID = "0198f000-0000-7000-8000-000000000000";
export const OFFICIAL_TARGET =
  "urn:li:dataset:(urn:li:dataPlatform:dbt,b2fd91.ORDER_ENTRY_DB.analytics.order_details,PROD)";

const downstream: AffectedAsset[] = [
  [
    "ORDER_DETAILS",
    "dataset",
    "Ecommerce Operations",
    "snowflake",
    2,
  ],
  ["ORDER_DETAILS_REPLICA", "dataset", null, "snowflake", 3],
  [
    "Customer Analytics Measures",
    "semantic_model",
    null,
    "powerbi",
    3,
  ],
  ["Geographic Measures", "semantic_model", null, "powerbi", 3],
  ["Essential KPI Measures", "semantic_model", null, "powerbi", 3],
  ["order_details", "view", "Data Platform Team", "looker", 3],
  ["Order Details", "explore", "Data Platform Team", "looker", 4],
].map(([name, entityType, domain, platform, pathLength], index) => {
  const urn = `urn:li:dataset:(urn:li:dataPlatform:${platform},showcase.asset-${index},PROD)`;
  return {
    urn,
    name: String(name),
    entity_type: String(entityType),
    domain: domain === null ? null : String(domain),
    field: index >= 2 && index <= 4 ? "CUST_EMAIL" : "cust_email",
    is_executive: false,
    is_production_ml: false,
    lineage_path: [
      OFFICIAL_TARGET,
      ...Array.from(
        { length: Number(pathLength) - 2 },
        (_, pathIndex) => `urn:li:dataset:path-${index}-${pathIndex}`,
      ),
      urn,
    ],
  };
});

const artifactContents: Record<string, string> = {
  "models/marts/order_details.sql": `select
    order_id,
    cust_email,
    cust_email as primary_email
from {{ ref('stg_order_details') }}
`,
  "models/marts/order_details.yml":
    "version: 2\nmodels:\n  - name: order_details\n",
  "tests/assert_cust_email_compatibility.sql":
    "select * from order_details where cust_email is distinct from primary_email\n",
  "migrations/2026-08-08-cust-email-rename.md":
    "# cust_email compatibility migration\n",
  "ROLLBACK.md": "# Rollback\nRestore all generated files together.\n",
  "PR_BODY.md":
    "# Safe cust_email rename\n<img src=x onerror=alert('unsafe')>\n",
  "changesafe-manifest.json": '{"files":{}}\n',
};

const files = Object.fromEntries(
  Object.entries(artifactContents).map(([path, content]) => [
    path,
    { path, content, sha256: "a".repeat(64) },
  ]),
);

const impacts: ImpactAssessment[] = [
  {
    category: "data_integrity",
    label: "Data integrity",
    severity: "critical",
    confidence: "direct",
    summary: "Seven recorded dependencies consume the current field contract.",
    qualifier: null,
    basis: "Schema and field-level lineage provide direct evidence.",
    evidence_urns: [OFFICIAL_TARGET, ...downstream.map((asset) => asset.urn)],
  },
  {
    category: "privacy_compliance",
    label: "Privacy & compliance",
    severity: "critical",
    confidence: "direct",
    summary: "The field carries direct personal-data governance evidence.",
    qualifier: null,
    basis: "The field is tagged PII and linked to a personal-data glossary term.",
    evidence_urns: ["urn:li:tag:b2fd91.PII_Data"],
  },
  {
    category: "operational_continuity",
    label: "Operational continuity",
    severity: "high",
    confidence: "direct",
    summary: "A compatibility window keeps frequent consumers operating.",
    qualifier: null,
    basis: "High usage and recorded dependency evidence are present.",
    evidence_urns: [OFFICIAL_TARGET, downstream[0].urn],
  },
  {
    category: "trust_decision_quality",
    label: "Trust & decision quality",
    severity: "high",
    confidence: "direct",
    summary: "Business analytics may become stale if contracts diverge.",
    qualifier: null,
    basis: "Power BI and Looker consumers use an authoritative field.",
    evidence_urns: downstream.slice(2).map((asset) => asset.urn),
  },
  {
    category: "financial_exposure",
    label: "Financial exposure",
    severity: "high",
    confidence: "inferred",
    summary: "Disruption may require business rework; metadata has no amount.",
    qualifier: "Potentially high, not quantified",
    basis: "Inference from usage and business-facing dependencies only.",
    evidence_urns: [OFFICIAL_TARGET, downstream[2].urn],
  },
  {
    category: "organizational_impact",
    label: "Organizational impact",
    severity: "high",
    confidence: "direct",
    summary: "The migration requires accountable cross-team coordination.",
    qualifier: null,
    basis: "Two owners and multiple consuming domains are recorded.",
    evidence_urns: [
      "urn:li:corpGroup:b2fd91.ORG_DATA_PLATFORM",
      "urn:li:corpuser:b2fd91.EMP006",
    ],
  },
];

export const goldenRun: RunView = {
  run_id: RUN_ID,
  state: "awaiting_approval",
  request: {
    asset_urn: OFFICIAL_TARGET,
    operation: "rename",
    field: "cust_email",
    new_field: "primary_email",
    old_type: null,
    new_type: null,
    source_commit: "showcase-ecommerce-safe-rename",
    requested_by: "judge-demo",
  },
  analysis: {
    context: {
      target_urn: OFFICIAL_TARGET,
      target_name: "order_details",
      target_domain: "Data Platform Team",
      field: "cust_email",
      field_type: "TEXT",
      schema_fields: [
        { name: "order_id", data_type: "NUMBER", nullable: false },
        { name: "cust_email", data_type: "TEXT", nullable: false },
        { name: "updated_at", data_type: "TIMESTAMP_LTZ", nullable: false },
      ],
      upstream_assets: [
        {
          urn: "urn:li:dataset:(urn:li:dataPlatform:dbt,changesafe.showcase_ecommerce.stg_order_details,PROD)",
          name: "stg_order_details",
          entity_type: "dataset",
          domain: "Data Platform Team",
          field: "cust_email",
          is_executive: false,
          is_production_ml: false,
          lineage_path: ["urn:li:dataset:staging", OFFICIAL_TARGET],
        },
      ],
      downstream_assets: downstream,
      owners: [
        {
          urn: "urn:li:corpGroup:b2fd91.ORG_DATA_PLATFORM",
          name: "Data Platform Team",
          ownership_type: "TECHNICAL_OWNER",
        },
        {
          urn: "urn:li:corpuser:b2fd91.EMP006",
          name: "Ian Chen",
          ownership_type: "BUSINESS_OWNER",
        },
      ],
      field_tags: [
        "urn:li:tag:b2fd91.PII_Data",
        "urn:li:tag:b2fd91.Authoritative Source",
      ],
      glossary_terms: ["urn:li:glossaryTerm:b2fd91.personal-data"],
      structured_properties: {},
      usage_tier: "high",
      queries: ["sanitized query evidence"],
      evidence: [
        { urn: OFFICIAL_TARGET, kind: "schema", label: "cust_email TEXT", path: [] },
        {
          urn: "urn:li:tag:b2fd91.PII_Data",
          kind: "governance",
          label: "PII Data",
          path: [],
        },
        ...downstream.map((asset) => ({
          urn: asset.urn,
          kind: "lineage",
          label: asset.name,
          path: asset.lineage_path,
        })),
      ],
      tool_evidence: [],
      provenance: {
        mode: "snapshot",
        retrieved_at: NOW,
        adapter_version: "datahub-agent-context/1.7.0",
        snapshot_hash: "b".repeat(64),
      },
    },
    risk: {
      score: 80,
      band: "high",
      recommended_strategy: "two_phase_compatibility_migration",
      factors: [
        ["base_rename", "Column rename", 25],
        ["downstream_assets", "7 downstream assets", 25],
        ["governed_field", "Governed or PII field", 10],
        ["high_usage", "High query usage", 10],
        ["cross_domain", "Cross-domain impact", 10],
      ].map(([code, label, points]) => ({
        code: String(code),
        label: String(label),
        points: Number(points),
        evidence_urns: [OFFICIAL_TARGET],
      })),
    },
    artifacts: { files, manifest_hash: "c".repeat(64) },
    validation: {
      passed: true,
      checks: Array.from({ length: 12 }, (_, index) => ({
        code: `check_${index + 1}`,
        label: `Safety check ${index + 1}`,
        passed: true,
        blocking: true,
        detail: "Passed against generated bytes.",
      })),
    },
    publication_eligible: true,
    impacts,
  },
  publication: null,
  error: null,
  created_at: NOW,
  updated_at: NOW,
};

export const previewReceipt: PublicationReceipt = {
  mode: "preview",
  idempotency_key: "d".repeat(64),
  artifact_hash: "c".repeat(64),
  branch: null,
  pull_request_url: null,
  patch: "diff --git a/model.sql b/model.sql\n",
  writeback: {
    mode: "preview",
    label: "NOT WRITTEN — SNAPSHOT MODE",
    document_urn: null,
    updated_urns: [goldenRun.request.asset_urn],
    mutations: [],
    idempotent_reuse: false,
  },
};

const eventDefinitions = [
  ["created", "Run created"],
  ["loading_context", "Reading the existing data contract"],
  ["scoring_risk", "Classifying business and technical impact"],
  ["generating", "Preparing a compatible migration"],
  ["validating", "Proving the generated change is safe"],
  ["awaiting_approval", "Waiting for the accountable owner"],
] as const;

export const goldenEvents: RunEvent[] = eventDefinitions.map(
  ([state, publicMessage], index) => ({
    run_id: RUN_ID,
    sequence: index + 1,
    state,
    public_message: publicMessage,
    evidence: state === "scoring_risk" ? goldenRun.analysis!.context.evidence : [],
    created_at: NOW,
  }),
);

export function createGoldenApi(): ChangeSafeApi {
  let current: RunView = {
    ...goldenRun,
    state: "created",
    analysis: null,
  };
  const publicConfig: PublicConfig = {
    mode: "replay",
    live_context_available: false,
    datahub_ui_url: null,
    llm_available: false,
    github_publication_available: false,
    datahub_writeback_available: false,
    owner_activity_available: false,
    openai_model: "gpt-5.6-luna",
  };
  return {
    getPublicConfig: vi.fn(async () => publicConfig),
    getOwnerActivity: vi.fn(async () => []),
    createRun: vi.fn(async () => current),
    getRun: vi.fn(async () => current),
    approve: vi.fn(async () => {
      current = {
        ...goldenRun,
        state: "completed",
        publication: previewReceipt,
      };
      return previewReceipt;
    }),
    continueWithSnapshot: vi.fn(async () => current),
    subscribe: (_runId, afterSequence, onEvent) => {
      queueMicrotask(() => {
        for (const event of goldenEvents) {
          if (event.sequence <= afterSequence) continue;
          if (event.state === "awaiting_approval") current = goldenRun;
          onEvent(event);
        }
      });
      return () => undefined;
    },
  };
}
