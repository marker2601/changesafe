import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RunTimeline } from "../src/components/RunTimeline";
import type { RunEvent } from "../src/types";
import {
  goldenEvents,
  passedWarehouseValidation,
  RUN_ID,
} from "./fixtures";

const loadingEvent: RunEvent = {
  run_id: RUN_ID,
  sequence: 2,
  state: "loading_context",
  public_message: "Reading the existing data contract",
  evidence: [],
  created_at: "2026-08-08T20:00:00Z",
};

describe("RunTimeline", () => {
  it("shows seven plain-language steps from persisted state", () => {
    render(
      <RunTimeline
        events={goldenEvents}
        field="cust_email"
        publicationMode="live"
        runState="awaiting_approval"
      />,
    );

    expect(screen.getAllByTestId("process-step")).toHaveLength(7);
    expect(
      screen.getByText("Finding everything that depends on cust_email").closest("li"),
    ).toHaveTextContent("Complete");
    expect(
      screen.getByText("Waiting for the accountable owner").closest("li"),
    ).toHaveTextContent("In progress");
    expect(
      screen.getByText("Publishing the approved change and evidence").closest("li"),
    ).toHaveTextContent("Pending");
    expect(
      screen.getByText("Publishing the approved change and evidence").closest("li"),
    ).toHaveTextContent("Step 07");
  });

  it("does not call a failed live context attempt complete", () => {
    render(
      <RunTimeline
        events={[loadingEvent]}
        field="cust_email"
        runState="context_fallback_required"
      />,
    );

    expect(
      screen.getByText("Reading the existing data contract").closest("li"),
    ).toHaveTextContent("Interrupted");
  });

  it("shows sequence-relative timing and follows the requested field", () => {
    const timedEvents: RunEvent[] = [
      { ...loadingEvent, sequence: 1, created_at: "2026-08-08T20:00:00.000Z" },
      {
        ...loadingEvent,
        sequence: 2,
        state: "scoring_risk",
        created_at: "2026-08-08T20:00:00.024Z",
      },
      {
        ...loadingEvent,
        sequence: 3,
        state: "generating",
        created_at: "2026-08-08T20:00:00.280Z",
      },
    ];

    render(
      <RunTimeline
        events={timedEvents}
        field="customer_email"
        runState="generating"
      />,
    );

    expect(screen.getAllByText("Event 02 · +24 ms").length).toBeGreaterThan(0);
    expect(screen.getByText("Event 03 · +280 ms")).toBeVisible();
    expect(
      screen.getByText("Finding everything that depends on customer_email"),
    ).toBeVisible();
  });

  it("keeps event sequence visible when timestamps are identical", () => {
    render(
      <RunTimeline
        events={[
          { ...loadingEvent, sequence: 8 },
          { ...loadingEvent, sequence: 9, state: "scoring_risk" },
        ]}
        field="cust_email"
        runState="scoring_risk"
      />,
    );

    expect(screen.getByText("Event 08 · +0 ms")).toBeVisible();
    expect(screen.getAllByText("Event 09 · +0 ms").length).toBeGreaterThan(0);
  });

  it("describes a persisted preview without publication language", () => {
    const { rerender } = render(
      <RunTimeline
        events={goldenEvents}
        field="cust_email"
        publicationMode="preview"
        runState="preparing_preview"
      />,
    );

    expect(
      screen.getByText("Preparing the approved preview and evidence").closest("li"),
    ).toHaveTextContent("In progress");
    expect(
      screen.queryByText("Publishing the approved change and evidence"),
    ).not.toBeInTheDocument();

    rerender(
      <RunTimeline
        events={goldenEvents}
        field="cust_email"
        publicationMode="preview"
        runState="completed"
      />,
    );

    expect(
      screen.getByText("Preparing the approved preview and evidence").closest("li"),
    ).toHaveTextContent("Complete");
  });

  it("uses live publication language only for a live publication intent", () => {
    const { rerender } = render(
      <RunTimeline
        events={goldenEvents}
        field="cust_email"
        publicationMode={null}
        runState="awaiting_approval"
      />,
    );

    expect(screen.getByText("Finalizing the approved change package")).toBeVisible();
    expect(
      screen.queryByText("Publishing the approved change and evidence"),
    ).not.toBeInTheDocument();

    rerender(
      <RunTimeline
        events={goldenEvents}
        field="cust_email"
        publicationMode="live"
        runState="awaiting_approval"
      />,
    );

    expect(
      screen.getByText("Publishing the approved change and evidence"),
    ).toBeVisible();
  });

  it("interrupts the latest persisted phase when analysis fails", () => {
    const failedEvents: RunEvent[] = [
      { ...loadingEvent, sequence: 1, state: "created" },
      { ...loadingEvent, sequence: 2 },
      { ...loadingEvent, sequence: 3, state: "scoring_risk" },
      { ...loadingEvent, sequence: 4, state: "generating" },
      { ...loadingEvent, sequence: 5, state: "failed" },
    ];

    render(
      <RunTimeline
        events={failedEvents}
        field="cust_email"
        publicationMode="preview"
        runState="failed"
      />,
    );

    expect(screen.getByText("Preparing a compatible migration").closest("li"))
      .toHaveTextContent("Interrupted");
    expect(
      screen.getByText("Classifying business and technical impact").closest("li"),
    ).toHaveTextContent("Complete");
    expect(
      screen.getByText("Proving the generated change is safe").closest("li"),
    ).toHaveTextContent("Pending");
  });

  it("adds a persisted warehouse phase when policy requires it", () => {
    const warehouseEvent: RunEvent = {
      ...loadingEvent,
      sequence: 6,
      state: "validating_warehouse",
      public_message: "Validating aggregate warehouse evidence",
    };

    render(
      <RunTimeline
        events={[...goldenEvents.slice(0, -1), warehouseEvent]}
        field="account_status"
        runState="validating_warehouse"
        warehouseValidationRequired
      />,
    );

    expect(screen.getAllByTestId("process-step")).toHaveLength(8);
    expect(
      screen.getByText("Validating aggregate warehouse evidence").closest("li"),
    ).toHaveTextContent("In progress");
    expect(
      screen.getByText("Finding everything that depends on account_status"),
    ).toBeVisible();
  });

  it("interrupts a failed warehouse phase and keeps its event metadata", () => {
    const warehouseEvent: RunEvent = {
      ...loadingEvent,
      sequence: 6,
      state: "validating_warehouse",
      public_message: "Validating aggregate warehouse evidence",
    };

    render(
      <RunTimeline
        events={[...goldenEvents.slice(0, -1), warehouseEvent]}
        field="cust_email"
        runState="failed"
        warehouseValidation={passedWarehouseValidation}
      />,
    );

    const warehouseStep = screen
      .getByText("Validating aggregate warehouse evidence")
      .closest("li");
    expect(warehouseStep).toHaveTextContent("Interrupted");
    expect(warehouseStep).toHaveTextContent("Event 06");
  });
});
