import { describe, expect, it } from "vitest";

import { buildLineageRoute, formatEndpoint, formatRoute, lineageDegree } from "../src/lineageRoute";
import type { AffectedAsset, ContextBundle } from "../src/types";

const context: ContextBundle = {
  target_urn: "urn:li:dataset:(urn:li:dataPlatform:dbt,order_details,PROD)",
  target_name: "order_details",
  target_domain: "Data Platform Team",
  field: "cust_email",
  field_type: "VARCHAR",
  schema_fields: [],
  upstream_assets: [],
  downstream_assets: [],
  owners: [],
  field_tags: [],
  glossary_terms: [],
  structured_properties: {},
  usage_tier: "none",
  query_count: 0,
  evidence: [],
  tool_evidence: [],
  provenance: {
    mode: "snapshot",
    retrieved_at: "2026-08-09T00:00:00Z",
    adapter_version: "test",
    snapshot_hash: null,
  },
};

function asset(overrides: Partial<AffectedAsset> = {}): AffectedAsset {
  return {
    urn: "urn:li:dataset:(urn:li:dataPlatform:snowflake,ORDER_DETAILS,PROD)",
    name: "ORDER_DETAILS",
    entity_type: "dataset",
    domain: null,
    field: "cust_email",
    is_executive: false,
    is_production_ml: false,
    lineage_degree: 1,
    lineage_path: [
      context.target_urn,
      "urn:li:dataset:(urn:li:dataPlatform:snowflake,ORDER_DETAILS,PROD)",
    ],
    lineage_precision: "exact_field",
    ...overrides,
  };
}

describe("lineageRoute", () => {
  it("builds exact upstream and downstream endpoint order", () => {
    const upstreamAsset = asset({
      urn: "urn:li:dataset:(urn:li:dataPlatform:dbt,stg_order_details,PROD)",
      name: "stg_order_details",
      lineage_path: [
        "urn:li:dataset:(urn:li:dataPlatform:dbt,stg_order_details,PROD)",
        context.target_urn,
      ],
    });
    const downstreamAsset = asset();

    const upstream = buildLineageRoute(context, upstreamAsset, "upstream");
    const downstream = buildLineageRoute(context, downstreamAsset, "downstream");

    expect(upstream.source).toEqual({
      urn: upstreamAsset.urn,
      name: upstreamAsset.name,
      field: "cust_email",
    });
    expect(upstream.destination).toEqual({
      urn: context.target_urn,
      name: context.target_name,
      field: context.field,
    });
    expect(formatRoute(upstream)).toBe(
      "stg_order_details.cust_email → order_details.cust_email",
    );
    expect(downstream.source.urn).toBe(context.target_urn);
    expect(downstream.destination.urn).toBe(downstreamAsset.urn);
    expect(formatRoute(downstream)).toBe(
      "order_details.cust_email → ORDER_DETAILS.cust_email",
    );
  });

  it("discloses endpoint-only multi-hop evidence without inventing intermediate columns", () => {
    const route = buildLineageRoute(
      context,
      asset({
        name: "Customer Analytics Measures",
        urn: "urn:li:dataset:(urn:li:dataPlatform:powerbi,analytics,PROD)",
        field: "CUST_EMAIL",
        lineage_degree: 2,
        lineage_path: [
          context.target_urn,
          "urn:li:dataset:intermediate",
          "urn:li:dataset:(urn:li:dataPlatform:powerbi,analytics,PROD)",
        ],
        lineage_precision: "endpoint_field",
      }),
      "downstream",
    );

    expect(route.limitation).toBe(
      "2 hops; intermediate column mapping not returned by DataHub",
    );
    expect(formatRoute(route)).toBe(
      "order_details.cust_email → Customer Analytics Measures.CUST_EMAIL",
    );
  });

  it("discloses which field is unavailable for dataset-level routes", () => {
    const downstream = buildLineageRoute(
      context,
      asset({ field: null, lineage_degree: 1, lineage_path: [], lineage_precision: "dataset_level" }),
      "downstream",
    );
    const upstream = buildLineageRoute(
      context,
      asset({ field: null, lineage_degree: 1, lineage_path: [], lineage_precision: "dataset_level" }),
      "upstream",
    );

    expect(formatEndpoint(downstream.destination)).toBe("ORDER_DETAILS");
    expect(downstream.limitation).toBe(
      "Dataset-level relationship; destination field not returned by DataHub",
    );
    expect(upstream.limitation).toBe(
      "Dataset-level relationship; source field not returned by DataHub",
    );
  });

  it("keeps recorded multi-hop degree authoritative over a two-URN path", () => {
    const route = buildLineageRoute(
      context,
      asset({ lineage_degree: 2, lineage_path: [context.target_urn, "urn:li:dataset:endpoint"], lineage_precision: "endpoint_field" }),
      "downstream",
    );

    expect(route.degree).toBe(2);
    expect(route.orderedAssetPath).toEqual([context.target_urn, "urn:li:dataset:endpoint"]);
    expect(route.limitation).toContain("2 hops");
  });

  it("derives a concrete path degree only when the authoritative degree is absent", () => {
    expect(
      lineageDegree(
        asset({
          lineage_degree: null,
          lineage_path: [context.target_urn, "urn:li:dataset:middle", "urn:li:dataset:endpoint"],
        }),
      ),
    ).toBe(2);
  });

  it("keeps an explicit DataHub degree authoritative when a conflicting path is longer", () => {
    expect(
      lineageDegree(
        asset({
          lineage_degree: 1,
          lineage_path: [
            context.target_urn,
            "urn:li:dataset:unverified-intermediate",
            "urn:li:dataset:endpoint",
          ],
        }),
      ),
    ).toBe(1);
  });
});
