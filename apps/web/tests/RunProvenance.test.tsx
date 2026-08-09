import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { RunProvenance } from "../src/components/RunProvenance";
import { formatElapsed } from "../src/runTiming";
import type { PublicConfig } from "../src/types";
import { goldenRun } from "./fixtures";

const replayConfig: PublicConfig = {
  mode: "replay",
  live_context_available: false,
  datahub_ui_url: null,
  llm_available: false,
  github_publication_available: false,
  datahub_writeback_available: false,
  owner_activity_available: false,
  openai_model: "gpt-5.6-luna",
};

describe("RunProvenance", () => {
  it("explains a completed recorded-evidence run without false controls", async () => {
    const user = userEvent.setup();
    const run = {
      ...goldenRun,
      created_at: "2026-08-08T20:00:00.000Z",
      updated_at: "2026-08-08T20:00:00.280Z",
    };

    render(<RunProvenance busy={false} config={replayConfig} run={run} />);

    const evidence = screen.getByText("Recorded DataHub evidence");
    expect(evidence).toBeVisible();
    expect(evidence.closest("button")).toBeNull();
    expect(screen.getByText("Preview only")).toBeVisible();
    expect(screen.getByText("Completed in 0.28 seconds")).toBeVisible();
    expect(
      screen.getByText(
        "Same request + same evidence = same verified result.",
      ),
    ).toBeVisible();
    expect(screen.getByText(/^bbbbbbbb/)).toBeVisible();

    await user.click(screen.getByText("About this run"));
    expect(
      screen.getByText(/checksum-verified recording of DataHub metadata/i),
    ).toBeVisible();
    expect(
      screen.getByText(/performs no live DataHub reads or writes/i),
    ).toBeVisible();
  });

  it("formats elapsed durations at useful precision", () => {
    expect(formatElapsed(280)).toBe("0.28 seconds");
    expect(formatElapsed(1_240)).toBe("1.2 seconds");
    expect(formatElapsed(12_400)).toBe("12 seconds");
  });
});
