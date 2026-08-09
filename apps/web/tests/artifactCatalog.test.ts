import { describe, expect, it } from "vitest";

import { artifactExplanation } from "../src/artifactCatalog";

describe("artifactExplanation", () => {
  it.each([
    ["models/marts/order_details.sql", "dbt model SQL", "existing consumers"],
    ["models/marts/order_details.yml", "dbt model YAML", "SQL/YAML drift"],
    [
      "tests/assert_cust_email_retained.sql",
      "Compatibility test",
      "premature removal",
    ],
    ["migrations/cust-email.md", "Migration notes", "phase-two change"],
    ["ROLLBACK.md", "Rollback guide", "unsafe reversal"],
    ["PR_BODY.md", "Pull-request body", "reviewer context"],
    ["changesafe-manifest.json", "Verification manifest", "substitution"],
    ["notes/custom.txt", "Generated file", "unexplained file"],
  ])("explains %s", (path, label, preventedFailure) => {
    const explanation = artifactExplanation(path);

    expect(explanation.label).toBe(label);
    expect(explanation.purpose.length).toBeGreaterThan(20);
    expect(explanation.prevents).toContain(preventedFailure);
  });
});
