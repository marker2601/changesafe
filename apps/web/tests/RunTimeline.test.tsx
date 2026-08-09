import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RunTimeline } from "../src/components/RunTimeline";
import type { RunEvent } from "../src/types";
import { goldenEvents, RUN_ID } from "./fixtures";

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
      <RunTimeline events={goldenEvents} runState="awaiting_approval" />,
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
        runState="context_fallback_required"
      />,
    );

    expect(
      screen.getByText("Reading the existing data contract").closest("li"),
    ).toHaveTextContent("Interrupted");
  });
});
