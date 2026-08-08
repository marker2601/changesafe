import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RunTimeline } from "../src/components/RunTimeline";
import type { RunEvent } from "../src/types";
import { RUN_ID } from "./fixtures";

const loadingEvent: RunEvent = {
  run_id: RUN_ID,
  sequence: 2,
  state: "loading_context",
  public_message: "Loading DataHub context",
  evidence: [],
  created_at: "2026-08-08T12:00:00Z",
};

describe("RunTimeline", () => {
  it("reconstructs completed phases from a restored run state", () => {
    render(<RunTimeline events={[]} runState="awaiting_approval" />);

    expect(screen.getByText("Context loaded").closest("li")).toHaveTextContent(
      "Complete",
    );
    expect(screen.getByText("Risk scored").closest("li")).toHaveTextContent(
      "Complete",
    );
    expect(screen.getByText("Awaiting approval").closest("li")).toHaveTextContent(
      "In progress",
    );
  });

  it("does not call a failed live context attempt complete", () => {
    render(
      <RunTimeline
        events={[loadingEvent]}
        runState="context_fallback_required"
      />,
    );

    expect(screen.getByText("Context loaded").closest("li")).toHaveTextContent(
      "Pending",
    );
  });
});
