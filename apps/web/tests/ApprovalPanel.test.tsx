import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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
      datahub_ui_url: "https://datahub.example.com",
      llm_available: false,
      github_publication_available: true,
      datahub_writeback_available: true,
      owner_activity_available: true,
      openai_model: "gpt-5.6-luna",
      live_evidence_required: true,
      warehouse_validation_available: true,
      warehouse_validation_required: true,
      warehouse_environment_label: "competition-non-production",
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

  it("shows active publication progress instead of a resume action", () => {
    render(
      <ApprovalPanel
        busy
        config={null}
        onApprove={vi.fn()}
        onReset={vi.fn()}
        patchUrl="#"
        run={{ ...goldenRun, state: "publishing" }}
      />,
    );

    expect(screen.getByText("Publishing approved change")).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Publishing…" }),
    ).toBeDisabled();
    expect(
      screen.queryByRole("button", { name: "Resume publication" }),
    ).not.toBeInTheDocument();
  });

  it("keeps failed validation evidence and offers a fresh analysis", async () => {
    const user = userEvent.setup();
    const onReset = vi.fn();
    render(
      <ApprovalPanel
        busy={false}
        config={null}
        onApprove={vi.fn()}
        onReset={onReset}
        patchUrl="#"
        run={{
          ...goldenRun,
          state: "failed",
          error: {
            code: "VERIFICATION_FAILED",
            message: "Generated artifacts did not pass every blocking check.",
            retryable: false,
          },
        }}
      />,
    );

    expect(screen.getByText("Change package blocked")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "New analysis" }));
    expect(onReset).toHaveBeenCalledOnce();
  });

  it("disables approval and shows the first persisted policy blocker", () => {
    const run: RunView = {
      ...goldenRun,
      analysis: {
        ...goldenRun.analysis!,
        publication_eligible: false,
        approval_blockers: [
          {
            code: "LIVE_EVIDENCE_REQUIRED",
            message: "Live metadata evidence is required for approval.",
            retryable: true,
          },
          {
            code: "WAREHOUSE_EVIDENCE_REQUIRED",
            message: "Warehouse validation evidence is required for approval.",
            retryable: true,
          },
        ],
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

    expect(screen.getByRole("button", { name: "Approve preview" })).toBeDisabled();
    expect(
      screen.getByText("Live metadata evidence is required for approval."),
    ).toBeVisible();
    expect(screen.queryByText(/every blocking check passes/i)).not.toBeInTheDocument();
  });

  it("does not recover approval eligibility from a completed state alone", () => {
    render(
      <ApprovalPanel
        busy={false}
        config={null}
        onApprove={vi.fn()}
        onReset={vi.fn()}
        patchUrl="#"
        run={{
          ...goldenRun,
          state: "completed",
          publication: null,
          analysis: {
            ...goldenRun.analysis!,
            publication_eligible: false,
            approval_blockers: [
              {
                code: "WAREHOUSE_VALIDATION_FAILED",
                message: "Warehouse validation did not pass.",
                retryable: false,
              },
            ],
          },
        }}
      />,
    );

    expect(screen.getByRole("button", { name: "Approve preview" })).toBeDisabled();
    expect(screen.getByText("Warehouse validation did not pass.")).toBeVisible();
  });
});
