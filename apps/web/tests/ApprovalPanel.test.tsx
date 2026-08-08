import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ApprovalPanel } from "../src/components/ApprovalPanel";
import type { PublicConfig, RunView } from "../src/types";
import { goldenRun } from "./fixtures";

describe("ApprovalPanel", () => {
  it("renders owner-token input when retrying a live publication", () => {
    const run: RunView = {
      ...goldenRun,
      state: "publication_failed",
      analysis: goldenRun.analysis
        ? {
            ...goldenRun.analysis,
            context: {
              ...goldenRun.analysis.context,
              provenance: {
                ...goldenRun.analysis.context.provenance,
                mode: "live",
                snapshot_hash: null,
              },
            },
          }
        : null,
      error: {
        code: "DATAHUB_WRITEBACK_FAILED",
        message: "DataHub writeback did not complete.",
        retryable: true,
      },
    };
    const config: PublicConfig = {
      mode: "live",
      live_context_available: true,
      llm_available: false,
      github_publication_available: true,
      datahub_writeback_available: true,
      openai_model: "gpt-5.6-luna",
    };

    render(
      <ApprovalPanel
        busy={false}
        config={config}
        onApprove={vi.fn()}
        onReset={vi.fn()}
        patchUrl="#"
        run={run}
      />,
    );

    expect(screen.getByLabelText("Owner token")).toHaveAttribute(
      "type",
      "password",
    );
    expect(
      screen.getByRole("button", { name: "Retry missing step" }),
    ).toBeEnabled();
  });

  it("disables retry and requests operator action for permanent failures", () => {
    const run: RunView = {
      ...goldenRun,
      state: "publication_failed",
      error: {
        code: "GITHUB_BRANCH_CONFLICT",
        message: "The branch no longer matches verified artifacts.",
        retryable: false,
      },
    };

    render(
      <ApprovalPanel
        busy={false}
        config={null}
        onApprove={vi.fn()}
        onReset={vi.fn()}
        patchUrl="#"
        run={run}
      />,
    );

    expect(
      screen.getByRole("button", { name: "Operator action required" }),
    ).toBeDisabled();
    expect(screen.getByText(/Retry is disabled/)).toBeVisible();
  });
});
