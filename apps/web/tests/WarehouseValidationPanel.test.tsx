import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { WarehouseValidationPanel } from "../src/components/WarehouseValidationPanel";
import type { WarehouseValidationResult } from "../src/types";
import {
  notRunWarehouseValidation,
  passedWarehouseValidation,
} from "./fixtures";

describe("WarehouseValidationPanel", () => {
  it("claims warehouse values were checked only for passed aggregate evidence", () => {
    const { container } = render(
      <WarehouseValidationPanel
        contextMode="live"
        validation={passedWarehouseValidation}
      />,
    );

    const panel = screen.getByRole("region", { name: "Warehouse validation" });
    expect(
      within(panel).getByText(
        "Warehouse values checked · competition-non-production",
      ),
    ).toBeVisible();
    expect(within(panel).getByText("cust_email")).toBeVisible();
    expect(within(panel).getByText("Rename")).toBeVisible();
    expect(within(panel).getByText("Rows evaluated").closest("div")).toHaveTextContent(
      "20",
    );
    expect(within(panel).getByText("Populated rows").closest("div")).toHaveTextContent(
      "20",
    );
    expect(within(panel).getByText("Unsafe rows").closest("div")).toHaveTextContent(
      "0",
    );
    expect(within(panel).getByText("Elapsed").closest("div")).toHaveTextContent(
      "18 ms",
    );
    expect(within(panel).getByText("Aggregate validation").closest("ol")).toHaveTextContent(
      "Aggregate validation",
    );

    const audit = within(panel).getByText("Technical audit identifiers").closest(
      "details",
    );
    expect(audit).not.toHaveAttribute("open");
    expect(audit).toHaveTextContent("warehouse-query-01");
    expect(container).not.toHaveTextContent("f".repeat(64));
  });

  it("says production rows were not queried when warehouse validation did not run", () => {
    render(
      <WarehouseValidationPanel
        contextMode="snapshot"
        validation={notRunWarehouseValidation}
      />,
    );

    expect(screen.getByText("Production rows not queried")).toBeVisible();
    expect(screen.queryByText(/Warehouse values checked/)).not.toBeInTheDocument();
    expect(screen.queryByText("Rows evaluated")).not.toBeInTheDocument();
  });

  it("does not imply row evidence for a result blocked before the aggregate query", () => {
    const blockedBeforeQuery: WarehouseValidationResult = {
      ...notRunWarehouseValidation,
      status: "blocked",
      mode: "aggregate",
      started_at: "2026-08-08T20:00:00Z",
      completed_at: "2026-08-08T20:00:00.004Z",
      elapsed_ms: 4,
      query_ids: ["identity-query-01"],
      checks: [
        {
          code: "warehouse_identity",
          label: "Warehouse identity",
          passed: false,
          retryable: false,
          detail: "Configured warehouse identity did not match.",
          observed_count: null,
        },
      ],
    };

    render(
      <WarehouseValidationPanel contextMode="live" validation={blockedBeforeQuery} />,
    );

    expect(screen.getByText("Production rows not queried")).toBeVisible();
    expect(screen.getByText(/blocked before aggregate production-row evidence/i)).toBeVisible();
    expect(screen.queryByText(/Warehouse values checked/)).not.toBeInTheDocument();
  });

  it("shows returned aggregate counts but labels all-null evidence inconclusive", () => {
    const blockedAfterQuery: WarehouseValidationResult = {
      ...passedWarehouseValidation,
      status: "blocked",
      rows_evaluated: 0,
      populated_row_count: 0,
      unsafe_row_count: 0,
      checks: [
        {
          code: "aggregate_evidence_empty",
          label: "Aggregate evidence",
          passed: false,
          retryable: false,
          detail: "Aggregate evidence was empty and inconclusive.",
          observed_count: 0,
        },
      ],
    };

    render(
      <WarehouseValidationPanel contextMode="live" validation={blockedAfterQuery} />,
    );

    expect(
      screen.getByText(
        "Warehouse validation inconclusive · competition-non-production",
      ),
    ).toBeVisible();
    expect(screen.getByText("Rows evaluated").closest("div")).toHaveTextContent("0");
    expect(screen.getByText(/approval remains blocked/i)).toBeVisible();
    expect(screen.queryByText(/Warehouse values checked/)).not.toBeInTheDocument();
  });

  it("uses the execution boundary for an aggregate-phase relation failure", () => {
    const aggregateRelationFailure: WarehouseValidationResult = {
      ...notRunWarehouseValidation,
      status: "blocked",
      mode: "aggregate",
      aggregate_query_started: true,
      started_at: "2026-08-08T20:00:00Z",
      completed_at: "2026-08-08T20:00:00.004Z",
      elapsed_ms: 4,
      checks: [
        {
          code: "warehouse_relation",
          label: "Warehouse relation",
          passed: false,
          retryable: false,
          detail: "Warehouse relation validation failed.",
          observed_count: null,
        },
      ],
    };

    render(
      <WarehouseValidationPanel
        contextMode="live"
        validation={aggregateRelationFailure}
      />,
    );

    expect(
      screen.getByText(
        "Warehouse validation inconclusive · competition-non-production",
      ),
    ).toBeVisible();
    expect(screen.queryByText("Production rows not queried")).not.toBeInTheDocument();
    expect(screen.queryByText(/Warehouse values checked/)).not.toBeInTheDocument();
  });

  it("treats a missing legacy execution boundary as unknown", () => {
    const legacyUnknown: WarehouseValidationResult = {
      ...passedWarehouseValidation,
      aggregate_query_started: null,
    };

    render(
      <WarehouseValidationPanel contextMode="live" validation={legacyUnknown} />,
    );

    expect(
      screen.getByText(
        "Warehouse query status unavailable · competition-non-production",
      ),
    ).toBeVisible();
    expect(screen.queryByText("Production rows not queried")).not.toBeInTheDocument();
    expect(screen.queryByText(/Warehouse values checked/)).not.toBeInTheDocument();
  });

  it("never calls snapshot evidence warehouse values checked", () => {
    render(
      <WarehouseValidationPanel
        contextMode="snapshot"
        validation={passedWarehouseValidation}
      />,
    );

    expect(
      screen.getByText(
        "Warehouse validation inconclusive · competition-non-production",
      ),
    ).toBeVisible();
    expect(screen.queryByText(/Warehouse values checked/)).not.toBeInTheDocument();
  });
});
