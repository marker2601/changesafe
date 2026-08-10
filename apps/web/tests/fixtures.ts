import { vi } from "vitest";

import type {
  AffectedAsset,
  ChangeSafeApi,
  ImpactAssessment,
  PublicConfig,
  PublicationReceipt,
  RunEvent,
  RunView,
  SchemaCatalog,
  WarehouseValidationResult,
} from "../src/types";

const NOW = "2026-08-08T20:00:00Z";
export const RUN_ID = "0198f000-0000-7000-8000-000000000000";
export const OFFICIAL_TARGET =
  "urn:li:dataset:(urn:li:dataPlatform:dbt,b2fd91.ORDER_ENTRY_DB.analytics.order_details,PROD)";

export const notRunWarehouseValidation = {
  status: "not_run",
  mode: "none",
  environment_label: "competition-non-production",
  operation: "rename",
  field: "cust_email",
  aggregate_query_started: false,
  started_at: null,
  completed_at: null,
  rows_evaluated: null,
  populated_row_count: null,
  unsafe_row_count: null,
  query_ids: [],
  elapsed_ms: null,
  checks: [],
} satisfies WarehouseValidationResult;

export const passedWarehouseValidation = {
  ...notRunWarehouseValidation,
  status: "passed",
  mode: "aggregate",
  aggregate_query_started: true,
  started_at: "2026-08-08T20:00:00Z",
  completed_at: "2026-08-08T20:00:00.018Z",
  rows_evaluated: 20,
  populated_row_count: 20,
  unsafe_row_count: 0,
  query_ids: ["warehouse-query-01"],
  elapsed_ms: 18,
  checks: [
    {
      code: "aggregate_validation",
      label: "Aggregate validation",
      passed: true,
      retryable: false,
      detail: "Aggregate checks passed.",
      observed_count: 0,
    },
  ],
} satisfies WarehouseValidationResult;

export const schemaFields = [
  { name: "order_id", data_type: "NUMBER", nullable: false },
  { name: "order_date", data_type: "TEXT", nullable: false },
  { name: "order_mode", data_type: "TEXT", nullable: false },
  { name: "order_status", data_type: "NUMBER", nullable: false },
  { name: "order_total", data_type: "FLOAT", nullable: false },
  { name: "cost_of_delivery", data_type: "FLOAT", nullable: false },
  { name: "delivery_type", data_type: "TEXT", nullable: false },
  { name: "wait_till_complete_yn", data_type: "TEXT", nullable: false },
  { name: "payment_method_code", data_type: "TEXT", nullable: false },
  { name: "customer_id", data_type: "NUMBER", nullable: false },
  { name: "cust_first_name", data_type: "TEXT", nullable: false },
  { name: "cust_last_name", data_type: "TEXT", nullable: false },
  { name: "cust_email", data_type: "TEXT", nullable: false },
  { name: "phone_number", data_type: "TEXT", nullable: false },
  { name: "customer_class", data_type: "TEXT", nullable: false },
  { name: "billing_address_line1", data_type: "TEXT", nullable: false },
  { name: "billing_address_line2", data_type: "TEXT", nullable: false },
  { name: "billing_town_city", data_type: "TEXT", nullable: false },
  { name: "billing_country", data_type: "TEXT", nullable: false },
  { name: "billing_zipcode", data_type: "NUMBER", nullable: false },
  { name: "billing_region", data_type: "TEXT", nullable: false },
  { name: "shipping_address_line1", data_type: "TEXT", nullable: false },
  { name: "shipping_address_line2", data_type: "TEXT", nullable: false },
  { name: "shipping_town_city", data_type: "TEXT", nullable: false },
  { name: "shipping_country", data_type: "TEXT", nullable: false },
  { name: "shipping_zipcode", data_type: "NUMBER", nullable: false },
  { name: "shipping_region", data_type: "TEXT", nullable: false },
  { name: "warehouse_id", data_type: "NUMBER", nullable: false },
  { name: "warehouse_name", data_type: "TEXT", nullable: false },
  { name: "promotion_id", data_type: "NUMBER", nullable: false },
  { name: "promotion_name", data_type: "TEXT", nullable: false },
  { name: "promotion_description", data_type: "TEXT", nullable: false },
  { name: "line_item_id", data_type: "NUMBER", nullable: false },
  { name: "product_id", data_type: "NUMBER", nullable: false },
  { name: "product_name", data_type: "TEXT", nullable: false },
  { name: "product_description", data_type: "TEXT", nullable: false },
  { name: "category_id", data_type: "NUMBER", nullable: false },
  { name: "category_name", data_type: "TEXT", nullable: false },
  { name: "unit_price", data_type: "FLOAT", nullable: false },
  { name: "quantity", data_type: "NUMBER", nullable: false },
  { name: "line_total", data_type: "FLOAT", nullable: false },
  { name: "dispatch_date", data_type: "TEXT", nullable: false },
  { name: "return_date", data_type: "TEXT", nullable: false },
  { name: "gift_wrap", data_type: "TEXT", nullable: false },
  { name: "condition", data_type: "TEXT", nullable: false },
  { name: "estimated_delivery", data_type: "TEXT", nullable: false },
  { name: "list_price", data_type: "FLOAT", nullable: false },
  { name: "product_status", data_type: "TEXT", nullable: false },
  { name: "quantity_on_hand", data_type: "NUMBER", nullable: false },
  { name: "stock_status", data_type: "TEXT", nullable: false },
  { name: "discount_amount", data_type: "FLOAT", nullable: false },
  { name: "discount_percent", data_type: "FLOAT", nullable: false },
  { name: "delivery_status", data_type: "TEXT", nullable: false },
  { name: "return_status", data_type: "TEXT", nullable: false },
  { name: "updated_at", data_type: "TIMESTAMP_LTZ", nullable: false },
] satisfies SchemaCatalog["schema_fields"];

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
    lineage_degree: Number(pathLength) - 1,
    lineage_path: [
      OFFICIAL_TARGET,
      ...Array.from(
        { length: Number(pathLength) - 2 },
        (_, pathIndex) => `urn:li:dataset:path-${index}-${pathIndex}`,
      ),
      urn,
    ],
    lineage_precision:
      Number(pathLength) === 2 ? "exact_field" : "endpoint_field",
  };
});

const artifactContents: Record<string, string> = {
  "models/marts/order_details__changesafe.sql": `select
    order_id,
    cust_email,
    cust_email as primary_email
from {{ ref('order_details') }}
`,
  "models/marts/order_details__changesafe.yml":
    "version: 2\nmodels:\n  - name: order_details__changesafe\n",
  "tests/assert_cust_email_compatibility.sql":
    "select cust_email from {{ ref('order_details__changesafe') }} where cust_email is distinct from primary_email\n",
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
    summary:
      "Renaming cust_email to primary_email can alter the contract consumed by seven recorded dependencies.",
    qualifier: null,
    basis: "Schema and field-level lineage provide direct evidence.",
    evidence_urns: [OFFICIAL_TARGET, ...downstream.map((asset) => asset.urn)],
  },
  {
    category: "privacy_compliance",
    label: "Privacy & compliance",
    severity: "critical",
    confidence: "direct",
    summary:
      "Renaming cust_email to primary_email affects a field with direct personal-data governance evidence.",
    qualifier: null,
    basis: "The field is tagged PII and linked to a personal-data glossary term.",
    evidence_urns: ["urn:li:tag:b2fd91.PII_Data"],
  },
  {
    category: "operational_continuity",
    label: "Operational continuity",
    severity: "high",
    confidence: "direct",
    summary:
      "Renaming cust_email to primary_email requires a coordinated compatibility window to keep recorded consumers and frequent queries operating.",
    qualifier: null,
    basis: "High usage and recorded dependency evidence are present.",
    evidence_urns: [OFFICIAL_TARGET, downstream[0].urn],
  },
  {
    category: "trust_decision_quality",
    label: "Trust & decision quality",
    severity: "high",
    confidence: "direct",
    summary:
      "Renaming cust_email to primary_email can make business-facing semantic and analytics assets stale or incomplete if their contracts diverge.",
    qualifier: null,
    basis: "Power BI and Looker consumers use an authoritative field.",
    evidence_urns: downstream.slice(2).map((asset) => asset.urn),
  },
  {
    category: "financial_exposure",
    label: "Financial exposure",
    severity: "high",
    confidence: "inferred",
    summary:
      "Renaming cust_email to primary_email may disrupt business workflows or require rework, but metadata cannot establish a monetary amount.",
    qualifier: "Potentially high, not quantified",
    basis: "Inference from usage and business-facing dependencies only.",
    evidence_urns: [OFFICIAL_TARGET, downstream[2].urn],
  },
  {
    category: "organizational_impact",
    label: "Organizational impact",
    severity: "high",
    confidence: "direct",
    summary:
      "Renaming cust_email to primary_email requires accountable coordination across the recorded owners and consuming domains.",
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
      schema_fields: schemaFields,
      upstream_assets: [
        {
          urn: "urn:li:dataset:(urn:li:dataPlatform:dbt,changesafe.showcase_ecommerce.stg_order_details,PROD)",
          name: "stg_order_details",
          entity_type: "dataset",
          domain: "Data Platform Team",
          field: "cust_email",
          is_executive: false,
          is_production_ml: false,
          lineage_degree: 1,
          lineage_path: ["urn:li:dataset:staging", OFFICIAL_TARGET],
          lineage_precision: "exact_field",
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
      query_count: 1,
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
    warehouse_validation: notRunWarehouseValidation,
    approval_blockers: [],
    impacts,
  },
  publication: null,
  error: null,
  created_at: NOW,
  updated_at: NOW,
};

export const goldenSchemaCatalog: SchemaCatalog = {
  target_urn: OFFICIAL_TARGET,
  target_name: "order_details",
  schema_fields: schemaFields,
  provenance: goldenRun.analysis!.context.provenance,
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
    live_evidence_required: false,
    warehouse_validation_available: false,
    warehouse_validation_required: false,
    warehouse_environment_label: "competition-non-production",
  };
  return {
    getPublicConfig: vi.fn(async () => publicConfig),
    getSchemaCatalog: vi.fn(async () => goldenSchemaCatalog),
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
