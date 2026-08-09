import { describe, expect, it } from "vitest";

import {
  changeSummary,
  DEFAULT_CHANGE_DRAFT,
  draftToRequest,
  isOfficialDataset,
  sourceCommitForOperation,
} from "../src/changeDraft";

describe("change draft presentation", () => {
  it("describes each supported operation in plain language", () => {
    expect(
      changeSummary({ ...DEFAULT_CHANGE_DRAFT, operation: "rename" }),
    ).toBe(
      "Keep cust_email available while consumers move to primary_email.",
    );
    expect(
      changeSummary({ ...DEFAULT_CHANGE_DRAFT, operation: "remove" }),
    ).toBe(
      "Delay removal of cust_email until every recorded consumer has migrated.",
    );
    expect(
      changeSummary({ ...DEFAULT_CHANGE_DRAFT, operation: "type_change" }),
    ).toBe(
      "Keep cust_email and add a safely cast VARCHAR(320) compatibility field during phase one.",
    );
  });

  it("asks for a rename destination before analysis when the field is incomplete", () => {
    expect(
      changeSummary({
        ...DEFAULT_CHANGE_DRAFT,
        field: "order_total",
        new_field: "",
      }),
    ).toBe("Choose the new field name for order_total before analysis.");
  });

  it("asks for a type destination before analysis when the field is incomplete", () => {
    expect(
      changeSummary({
        ...DEFAULT_CHANGE_DRAFT,
        field: "order_total",
        operation: "type_change",
        new_type: "",
      }),
    ).toBe("Choose the new type for order_total before analysis.");
  });

  it("uses operation-specific source commits", () => {
    expect(sourceCommitForOperation("rename")).toBe(
      "showcase-ecommerce-safe-rename",
    );
    expect(sourceCommitForOperation("remove")).toBe(
      "showcase-ecommerce-safe-remove",
    );
    expect(sourceCommitForOperation("type_change")).toBe(
      "showcase-ecommerce-safe-type-change",
    );
  });

  it("recognizes the official dataset without treating every selected field as the default scenario", () => {
    const anotherOfficialField = {
      ...DEFAULT_CHANGE_DRAFT,
      field: "order_total",
    };
    expect(isOfficialDataset(anotherOfficialField)).toBe(true);
    expect(
      isOfficialDataset({
        ...DEFAULT_CHANGE_DRAFT,
        asset_urn: "urn:li:dataset:other",
      }),
    ).toBe(false);
  });

  it("normalizes irrelevant fields before submission", () => {
    expect(
      draftToRequest({
        ...DEFAULT_CHANGE_DRAFT,
        operation: "remove",
        source_commit: sourceCommitForOperation("remove"),
      }),
    ).toEqual({
      asset_urn: DEFAULT_CHANGE_DRAFT.asset_urn,
      operation: "remove",
      field: "cust_email",
      new_field: null,
      old_type: null,
      new_type: null,
      source_commit: "showcase-ecommerce-safe-remove",
      requested_by: "changesafe-web",
    });
  });
});
