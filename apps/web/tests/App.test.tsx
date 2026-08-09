import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { App } from "../src/App";
import { RUN_SESSION_KEY } from "../src/hooks/useRun";
import type {
  ChangeSafeApi,
  PublicConfig,
  RunEvent,
  RunView,
} from "../src/types";
import { createGoldenApi, goldenRun, RUN_ID } from "./fixtures";

describe("ChangeSafe workspace", () => {
  it("keeps the ready scenario synchronized with the selected operation", async () => {
    const user = userEvent.setup();
    render(<App api={createGoldenApi()} />);

    await user.selectOptions(screen.getByLabelText("Operation"), "remove");

    expect(
      screen.getAllByText(
        "Delay removal of cust_email until every recorded consumer has migrated.",
      ).length,
    ).toBeGreaterThan(0);
    expect(
      screen.queryByText("Official judge scenario ready"),
    ).not.toBeInTheDocument();
  });

  it("blocks a new analysis while a saved run is being restored", async () => {
    let resolveRun: (run: RunView) => void = () => undefined;
    const pendingRun = new Promise<RunView>((resolve) => {
      resolveRun = resolve;
    });
    const api = {
      ...createGoldenApi(),
      getRun: vi.fn(() => pendingRun),
    };
    const subscribe = vi.spyOn(api, "subscribe");
    window.sessionStorage.setItem(
      RUN_SESSION_KEY,
      JSON.stringify({ runId: RUN_ID, lastSequence: 6 }),
    );

    render(<App api={api} />);

    expect(screen.getByRole("button", { name: /Analyzing/ })).toBeDisabled();
    await act(async () => resolveRun(goldenRun));
    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: "Change data safely, with every dependency in view.",
      }),
    ).toBeVisible();
    await waitFor(() =>
      expect(subscribe).toHaveBeenCalledWith(
        RUN_ID,
        0,
        expect.any(Function),
        expect.any(Function),
      ),
    );
  });

  it("restores an interrupted publication and resumes from its saved cursor", async () => {
    const subscribe = vi.fn(() => () => undefined);
    const publishing: RunView = {
      ...goldenRun,
      state: "publishing",
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
    };
    const api: ChangeSafeApi = {
      getPublicConfig: vi.fn(async (): Promise<PublicConfig> => ({
        mode: "live",
        live_context_available: true,
        datahub_ui_url: "https://datahub.example.com",
        llm_available: false,
        github_publication_available: true,
        datahub_writeback_available: true,
        owner_activity_available: true,
        openai_model: "gpt-5.6-luna",
      })),
      getOwnerActivity: vi.fn(async () => []),
      createRun: vi.fn(async () => publishing),
      getRun: vi.fn(async () => publishing),
      approve: vi.fn(async () => {
        throw new Error("not used");
      }),
      continueWithSnapshot: vi.fn(async () => publishing),
      subscribe,
    };
    window.sessionStorage.setItem(
      RUN_SESSION_KEY,
      JSON.stringify({ runId: RUN_ID, lastSequence: 7 }),
    );

    render(<App api={api} />);

    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: "Change data safely, with every dependency in view.",
      }),
    ).toBeVisible();
    await waitFor(() =>
      expect(subscribe).toHaveBeenCalledWith(
        RUN_ID,
        0,
        expect.any(Function),
        expect.any(Function),
      ),
    );
    expect(
      screen.getByRole("button", { name: "Resume publication" }),
    ).toBeEnabled();
    expect(screen.getByText("Owner-gated publishing")).toBeVisible();
  });

  it("restores a publication failure and rebuilds its event history", async () => {
    const failed: RunView = {
      ...goldenRun,
      state: "publication_failed",
      error: {
        code: "GITHUB_BRANCH_CONFLICT",
        message: "The branch no longer matches verified artifacts.",
        retryable: false,
      },
    };
    const subscribe = vi.fn(() => () => undefined);
    const api: ChangeSafeApi = {
      getPublicConfig: vi.fn(async (): Promise<PublicConfig> => ({
        mode: "live",
        live_context_available: true,
        datahub_ui_url: "https://datahub.example.com",
        llm_available: false,
        github_publication_available: true,
        datahub_writeback_available: true,
        owner_activity_available: true,
        openai_model: "gpt-5.6-luna",
      })),
      getOwnerActivity: vi.fn(async () => []),
      createRun: vi.fn(async () => failed),
      getRun: vi.fn(async () => failed),
      approve: vi.fn(async () => {
        throw new Error("not used");
      }),
      continueWithSnapshot: vi.fn(async () => failed),
      subscribe,
    };
    window.sessionStorage.setItem(
      RUN_SESSION_KEY,
      JSON.stringify({ runId: RUN_ID, lastSequence: 9 }),
    );

    render(<App api={api} />);

    expect(
      await screen.findByText("The branch no longer matches verified artifacts."),
    ).toBeVisible();
    await waitFor(() =>
      expect(subscribe).toHaveBeenCalledWith(
        RUN_ID,
        0,
        expect.any(Function),
        expect.any(Function),
      ),
    );
    expect(screen.getByText(`Run ID: ${RUN_ID.slice(0, 8)}`)).toBeVisible();
  });

  it("renders the real golden analysis from ordered run events", async () => {
    const user = userEvent.setup();
    render(<App api={createGoldenApi()} />);

    await user.click(screen.getByRole("button", { name: "Analyze change" }));

    expect(
      await screen.findByRole("heading", {
        name: "Change data safely, with every dependency in view.",
      }),
    ).toBeVisible();
    expect(screen.getByText("Official DataHub showcase-ecommerce")).toBeVisible();
    expect(screen.getAllByText("Order Entry Analytics").length).toBeGreaterThan(0);
    expect(screen.getAllByText("cust_email").length).toBeGreaterThan(0);
    expect(screen.getAllByText("primary_email").length).toBeGreaterThan(0);
    expect(screen.getAllByTestId("impact-category")).toHaveLength(6);
    expect(screen.getByText("Potentially high, not quantified")).toBeVisible();
    expect(screen.getAllByText("Customer Analytics Measures").length).toBeGreaterThan(0);
    expect(screen.getByText("12 / 12")).toBeVisible();
    expect(screen.getByText("Snapshot replay")).toBeVisible();
    expect(screen.getByText("Preview only / snapshot mode")).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Approve preview" }),
    ).toBeEnabled();
  });

  it("approves without credentials and labels snapshot writeback truthfully", async () => {
    const user = userEvent.setup();
    render(<App api={createGoldenApi()} />);
    await user.click(screen.getByRole("button", { name: "Analyze change" }));
    await user.click(
      await screen.findByRole("button", { name: "Approve preview" }),
    );

    expect(await screen.findByText("Preview ready")).toBeVisible();
    expect(screen.getByText("NOT WRITTEN — SNAPSHOT MODE")).toBeVisible();
    expect(
      screen.getByText("No external systems were changed."),
    ).toBeVisible();
  });

  it("renders generated code as text rather than injected HTML", async () => {
    const user = userEvent.setup();
    const api = createGoldenApi();
    render(<App api={api} />);
    await user.click(screen.getByRole("button", { name: "Analyze change" }));

    expect(await screen.findByText(/cust_email as primary_email/)).toBeVisible();
    await user.click(screen.getByRole("tab", { name: "PR_BODY.md" }));
    expect(screen.getByText(/<img src=x onerror=/)).toBeVisible();
    expect(document.querySelector(".artifact-code img")).toBeNull();
  });

  it("requires explicit confirmation before using the labeled snapshot", async () => {
    const user = userEvent.setup();
    const fallback: RunView = {
      ...goldenRun,
      state: "context_fallback_required",
      analysis: null,
      error: {
        code: "LIVE_CONTEXT_UNAVAILABLE",
        message:
          "Live metadata context is unavailable. Snapshot replay requires confirmation.",
        retryable: true,
      },
    };
    const event: RunEvent = {
      run_id: RUN_ID,
      sequence: 2,
      state: "context_fallback_required",
      public_message: "Live context unavailable; confirmation required",
      evidence: [],
      created_at: fallback.updated_at,
    };
    let current = fallback;
    const continueWithSnapshot = vi.fn(async () => {
      current = { ...fallback, state: "loading_context", error: null };
      return current;
    });
    const api: ChangeSafeApi = {
      getPublicConfig: vi.fn(async (): Promise<PublicConfig> => ({
        mode: "auto",
        live_context_available: true,
        datahub_ui_url: null,
        llm_available: false,
        github_publication_available: false,
        datahub_writeback_available: false,
        owner_activity_available: false,
        openai_model: "gpt-5.6-luna",
      })),
      getOwnerActivity: vi.fn(async () => []),
      createRun: vi.fn(async () => fallback),
      getRun: vi.fn(async () => current),
      approve: vi.fn(async () => {
        throw new Error("unexpected approval");
      }),
      continueWithSnapshot,
      subscribe: (_runId, _after, onEvent) => {
        queueMicrotask(() => onEvent(event));
        return () => undefined;
      },
    };
    render(<App api={api} />);

    await user.click(screen.getByRole("button", { name: "Analyze change" }));
    const confirm = await screen.findByRole("button", {
      name: "Continue with labeled snapshot",
    });
    expect(screen.getByText("Live unavailable")).toBeVisible();
    expect(
      screen.getByText("Preview only / publication disabled"),
    ).toBeVisible();
    expect(
      screen.getByText("Reading the existing data contract").closest("li"),
    ).toHaveTextContent("Interrupted");
    expect(continueWithSnapshot).not.toHaveBeenCalled();

    await user.click(confirm);

    expect(continueWithSnapshot).toHaveBeenCalledWith(RUN_ID);
  });
});
