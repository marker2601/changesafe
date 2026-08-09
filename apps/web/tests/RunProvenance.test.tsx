import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { RunProvenance } from "../src/components/RunProvenance";
import { formatElapsed } from "../src/runTiming";
import type { PublicConfig, RunEvent, RunView } from "../src/types";
import { goldenEvents, goldenRun, previewReceipt } from "./fixtures";

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
    const timedEvents: RunEvent[] = [
      { ...goldenEvents[0], created_at: "2026-08-08T20:00:00.000Z" },
      { ...goldenEvents.at(-1)!, created_at: "2026-08-08T20:00:00.280Z" },
    ];

    render(
      <RunProvenance config={replayConfig} events={timedEvents} run={run} />,
    );

    const evidence = screen.getByText("Recorded DataHub evidence");
    expect(evidence).toBeVisible();
    expect(evidence.closest("button")).toBeNull();
    expect(screen.getByText("Preview only")).toBeVisible();
    expect(screen.getByText("Completed in 0.28 seconds")).toBeVisible();
    expect(screen.getByText("2026-08-08 20:00:00 UTC")).toBeVisible();
    expect(screen.getByText(/^bbbbbbbb/)).toBeVisible();

    await user.click(screen.getByText("About this run"));
    const reproducibility = screen.getByText(
      "Same request + same evidence = same verified result.",
    );
    expect(reproducibility).toBeVisible();
    expect(reproducibility.closest("details")).not.toBeNull();
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

  it("shows explicit unknown facts until public configuration loads", async () => {
    const user = userEvent.setup();
    render(<RunProvenance config={null} run={null} />);

    expect(screen.getAllByText("Loading configuration…")).toHaveLength(2);
    expect(screen.queryByText("Recorded DataHub evidence")).not.toBeInTheDocument();
    expect(screen.queryByText("Preview only")).not.toBeInTheDocument();

    await user.click(screen.getByText("About this run"));
    expect(
      screen.getByText(/evidence and publication mode are not inferred/i),
    ).toBeVisible();
  });

  it("labels live metadata without leaving a checksum pending forever", () => {
    const liveRun: RunView = {
      ...goldenRun,
      analysis: {
        ...goldenRun.analysis!,
        context: {
          ...goldenRun.analysis!.context,
          provenance: {
            ...goldenRun.analysis!.context.provenance,
            mode: "live",
            snapshot_hash: null,
          },
        },
      },
    };
    const liveConfig: PublicConfig = {
      ...replayConfig,
      mode: "live",
      live_context_available: true,
      github_publication_available: true,
    };

    render(<RunProvenance config={liveConfig} run={liveRun} />);

    expect(screen.getByText("Live DataHub metadata")).toBeVisible();
    expect(screen.getByText("Live retrieval")).toBeVisible();
    expect(screen.queryByText("Pending")).not.toBeInTheDocument();
  });

  it("discloses a live-read attempt before a recorded auto fallback", async () => {
    const user = userEvent.setup();
    const fallbackEvent: RunEvent = {
      ...goldenEvents[1],
      sequence: 3,
      state: "context_fallback_required",
      public_message: "Live context unavailable; confirmation required",
    };
    const autoConfig: PublicConfig = {
      ...replayConfig,
      mode: "auto",
      live_context_available: true,
    };

    render(
      <RunProvenance
        config={autoConfig}
        events={[...goldenEvents.slice(0, 2), fallbackEvent, ...goldenEvents.slice(2)]}
        run={goldenRun}
      />,
    );

    expect(screen.getByText("Recorded evidence after live fallback")).toBeVisible();
    await user.click(screen.getByText("About this run"));
    expect(screen.getByText(/a live DataHub read was attempted/i)).toBeVisible();
    expect(
      screen.queryByText(/performs no live DataHub reads or writes/i),
    ).not.toBeInTheDocument();
  });

  it("keeps a durable preview receipt authoritative over changed sink config", () => {
    const completedPreview: RunView = {
      ...goldenRun,
      state: "completed",
      publication: previewReceipt,
    };
    const driftedConfig: PublicConfig = {
      ...replayConfig,
      mode: "live",
      live_context_available: true,
      github_publication_available: true,
      datahub_writeback_available: true,
    };

    render(<RunProvenance config={driftedConfig} run={completedPreview} />);

    expect(screen.getByText("Preview only")).toBeVisible();
    expect(screen.queryByText("Owner-gated publishing")).not.toBeInTheDocument();
  });

  it("keeps a durable preview checkpoint authoritative over changed sink config", () => {
    const preparingPreview: RunView = {
      ...goldenRun,
      state: "preparing_preview",
      analysis: {
        ...goldenRun.analysis!,
        context: {
          ...goldenRun.analysis!.context,
          provenance: {
            ...goldenRun.analysis!.context.provenance,
            mode: "live",
            snapshot_hash: null,
          },
        },
      },
    };
    const driftedConfig: PublicConfig = {
      ...replayConfig,
      mode: "live",
      live_context_available: true,
      github_publication_available: true,
    };

    render(<RunProvenance config={driftedConfig} run={preparingPreview} />);

    expect(screen.getByText("Preview only")).toBeVisible();
    expect(screen.queryByText("Owner-gated publishing")).not.toBeInTheDocument();
  });

  it("keeps a durable live receipt authoritative when sinks later disappear", () => {
    const completedLive: RunView = {
      ...goldenRun,
      state: "completed",
      publication: {
        ...previewReceipt,
        mode: "live",
        writeback: { ...previewReceipt.writeback, mode: "live" },
      },
    };

    render(<RunProvenance config={replayConfig} run={completedLive} />);

    expect(screen.getByText("Owner-gated publishing")).toBeVisible();
    expect(screen.queryByText("Preview only")).not.toBeInTheDocument();
  });

  it("stops analysis timing at the persisted approval event", () => {
    const events: RunEvent[] = [
      {
        ...goldenEvents[0],
        created_at: "2026-08-08T20:00:00.000Z",
      },
      {
        ...goldenEvents.at(-1)!,
        created_at: "2026-08-08T20:00:00.280Z",
      },
    ];
    const awaitingApproval: RunView = {
      ...goldenRun,
      updated_at: "2026-08-08T20:01:30.000Z",
    };

    render(
      <RunProvenance
        config={replayConfig}
        events={events}
        run={awaitingApproval}
      />,
    );

    expect(screen.getByText("Completed in 0.28 seconds")).toBeVisible();
    expect(screen.queryByText(/Running for/i)).not.toBeInTheDocument();
  });

  it("keeps the closed hero facts structure stable before and after analysis", () => {
    const { container, rerender } = render(
      <RunProvenance config={replayConfig} run={null} />,
    );
    const beforeFacts = container.querySelectorAll(".run-provenance dl > div").length;
    const beforeDetails = container.querySelectorAll(".run-provenance > details").length;

    rerender(
      <RunProvenance config={replayConfig} events={goldenEvents} run={goldenRun} />,
    );

    expect(container.querySelectorAll(".run-provenance dl > div")).toHaveLength(
      beforeFacts,
    );
    expect(container.querySelectorAll(".run-provenance > details")).toHaveLength(
      beforeDetails,
    );
    expect(container.querySelector(".run-provenance > .reproducibility-note"))
      .not.toBeInTheDocument();
  });
});
