import { describe, expect, it } from "vitest";

import { safeDataHubLink } from "../src/dataHubLink";
import type { AffectedAsset } from "../src/types";

function asset(urn: string): AffectedAsset {
  return {
    urn,
    name: "evidence",
    entity_type: "dataset",
    domain: null,
    field: null,
    is_executive: false,
    is_production_ml: false,
    lineage_degree: null,
    lineage_path: [],
    lineage_precision: "dataset_level",
  };
}

describe("safeDataHubLink", () => {
  it.each([
    ["urn:li:dataset:(urn:li:dataPlatform:snowflake,orders,PROD)", "dataset"],
    ["urn:li:dashboard:(looker,orders)", "dashboard"],
    ["urn:li:chart:(looker,orders)", "chart"],
    ["urn:li:dataJob:(urn:li:dataFlow:(airflow,orders,PROD),load)", "datajob"],
  ])("uses the DataHub entity route for %s", (urn, entityRoute) => {
    expect(safeDataHubLink("https://datahub.example.com/some/path", asset(urn))).toBe(
      `https://datahub.example.com/${entityRoute}/${encodeURIComponent(urn)}`,
    );
  });

  it("omits unsupported entities and unsafe origins instead of guessing a route", () => {
    expect(
      safeDataHubLink("https://datahub.example.com", asset("urn:li:mlModel:model")),
    ).toBeNull();
    expect(
      safeDataHubLink("javascript:alert(1)", asset("urn:li:dataset:(platform,name,PROD)")),
    ).toBeNull();
  });
});
