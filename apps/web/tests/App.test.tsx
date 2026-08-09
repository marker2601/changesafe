import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { App } from "../src/App";
import { RUN_SESSION_KEY } from "../src/hooks/useRun";
import type {
  ChangeSafeApi,
  PublicationReceipt,
  PublicConfig,
  RunEvent,
  RunView,
} from "../src/types";
import {
  createGoldenApi,
  goldenEvents,
  goldenRun,
  goldenSchemaCatalog,
  previewReceipt,
  RUN_ID,
} from "./fixtures";

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

  it("removes preset claims when the draft no longer matches the official scenario", async () => {
    const user = userEvent.setup();
    render(<App api={createGoldenApi()} />);

    await user.clear(screen.getByLabelText("Current field"));
    await user.type(screen.getByLabelText("Current field"), "order_status");

    expect(screen.getByText("Custom change request")).toBeVisible();
    expect(screen.getAllByText("Pending DataHub context")).toHaveLength(3);
    expect(screen.queryByText("Order Entry Analytics")).not.toBeInTheDocument();
    expect(
      screen.queryByText("Official DataHub showcase-ecommerce"),
    ).not.toBeInTheDocument();
    expect(screen.getByText("Dataset verified during analysis")).toBeVisible();
    expect(
      screen.getByRole("heading", { name: "Context not loaded" }),
    ).toBeVisible();
  });

  it("keeps the product hero structurally stable after analysis", async () => {
    const user = userEvent.setup();
    render(<App api={createGoldenApi()} />);
    const before = document.querySelector(".product-hero");

    expect(before).toHaveClass("product-hero");
    expect(before).not.toHaveClass("is-compact");

    await user.click(screen.getByRole("button", { name: "Analyze change" }));
    await screen.findByText("12 / 12");

    const after = document.querySelector(".product-hero");
    expect(after).toHaveClass("product-hero");
    expect(after).not.toHaveClass("is-compact");
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
      getSchemaCatalog: vi.fn(async () => goldenSchemaCatalog),
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

  it("keeps a restored run authoritative while rebuilding historical events", async () => {
    const completed: RunView = {
      ...goldenRun,
      state: "completed",
      publication: previewReceipt,
    };
    let onEvent: ((event: RunEvent) => void) | null = null;
    const api: ChangeSafeApi = {
      ...createGoldenApi(),
      getRun: vi.fn(async () => completed),
      subscribe: (_runId, _after, nextEvent) => {
        onEvent = nextEvent;
        return () => undefined;
      },
    };
    window.sessionStorage.setItem(
      RUN_SESSION_KEY,
      JSON.stringify({ runId: RUN_ID, lastSequence: 6 }),
    );

    render(<App api={api} />);

    expect(await screen.findByText("Preview ready")).toBeVisible();
    await act(async () => onEvent?.(goldenEvents[0]));
    expect(screen.getByText("Preview ready")).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "Approve preview" }),
    ).not.toBeInTheDocument();

    await act(async () => onEvent?.(goldenEvents.at(-1)!));
    expect(await screen.findByText("Preview ready")).toBeVisible();
  });

  it("finishes a restored publication when another request completes it", async () => {
    const publishing: RunView = {
      ...goldenRun,
      state: "publishing",
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
    const completed: RunView = {
      ...publishing,
      state: "completed",
      publication: {
        ...previewReceipt,
        mode: "live",
        writeback: {
          ...previewReceipt.writeback,
          mode: "live",
          label: "WRITTEN TO DATAHUB",
        },
      },
    };
    let current = publishing;
    let onEvent: ((event: RunEvent) => void) | null = null;
    const getRun = vi.fn(async () => current);
    const api: ChangeSafeApi = {
      ...createGoldenApi(),
      getRun,
      subscribe: (_runId, _after, nextEvent) => {
        onEvent = nextEvent;
        return () => undefined;
      },
    };
    window.sessionStorage.setItem(
      RUN_SESSION_KEY,
      JSON.stringify({ runId: RUN_ID, lastSequence: 7 }),
    );

    render(<App api={api} />);

    expect(
      await screen.findByRole("button", { name: "Resume publication" }),
    ).toBeEnabled();
    await act(async () =>
      onEvent?.({
        ...goldenEvents.at(-1)!,
        sequence: 7,
        state: "publishing",
        public_message: "Publishing verified artifacts",
      }),
    );
    current = completed;
    await act(async () =>
      onEvent?.({
        ...goldenEvents.at(-1)!,
        sequence: 8,
        state: "completed",
        public_message: "Publication complete",
      }),
    );

    expect(await screen.findByText("Publication complete")).toBeVisible();
    expect(screen.getByText("WRITTEN TO DATAHUB")).toBeVisible();
    expect(getRun).toHaveBeenCalledTimes(2);
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
      getSchemaCatalog: vi.fn(async () => goldenSchemaCatalog),
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

  it("replays events beyond a historical fallback when restoring a completed analysis", async () => {
    const history: RunEvent[] = [
      { ...goldenEvents[0], created_at: "2026-08-08T20:00:00.000Z" },
      { ...goldenEvents[1], created_at: "2026-08-08T20:00:00.100Z" },
      {
        ...goldenEvents[1],
        sequence: 3,
        state: "context_fallback_required",
        public_message: "Live context unavailable; confirmation required",
        created_at: "2026-08-08T20:00:00.200Z",
      },
      {
        ...goldenEvents[1],
        sequence: 4,
        created_at: "2026-08-08T20:00:00.300Z",
      },
      {
        ...goldenEvents[2],
        sequence: 5,
        created_at: "2026-08-08T20:00:00.400Z",
      },
      {
        ...goldenEvents[3],
        sequence: 6,
        created_at: "2026-08-08T20:00:00.500Z",
      },
      {
        ...goldenEvents[4],
        sequence: 7,
        created_at: "2026-08-08T20:00:00.600Z",
      },
      {
        ...goldenEvents[5],
        sequence: 8,
        created_at: "2026-08-08T20:00:00.700Z",
      },
    ];
    const restored: RunView = {
      ...goldenRun,
      created_at: history[0].created_at,
      updated_at: history.at(-1)!.created_at,
    };
    const api: ChangeSafeApi = {
      ...createGoldenApi(),
      getRun: vi.fn(async () => restored),
      subscribe: (_runId, after, onEvent) => {
        let closed = false;
        queueMicrotask(() => {
          for (const event of history) {
            if (closed || event.sequence <= after) continue;
            onEvent(event);
          }
        });
        return () => {
          closed = true;
        };
      },
    };
    window.sessionStorage.setItem(
      RUN_SESSION_KEY,
      JSON.stringify({ runId: RUN_ID, lastSequence: 3 }),
    );

    render(<App api={api} />);

    expect(await screen.findByText("Event 08 · +700 ms")).toBeVisible();
    expect(screen.getByText("Completed in 0.70 seconds")).toBeVisible();
    expect(screen.getByText("Recorded evidence after live fallback")).toBeVisible();
  });

  it("labels a returned custom live context without the showcase badge", async () => {
    const customUrn =
      "urn:li:dataset:(urn:li:dataPlatform:dbt,custom.analytics.payments_daily,PROD)";
    const custom: RunView = {
      ...goldenRun,
      request: {
        ...goldenRun.request,
        asset_urn: customUrn,
        field: "payment_email",
        new_field: "billing_email",
        source_commit: "custom-live-change",
      },
      analysis: {
        ...goldenRun.analysis!,
        context: {
          ...goldenRun.analysis!.context,
          target_urn: customUrn,
          target_name: "payments_daily",
          field: "payment_email",
          provenance: {
            ...goldenRun.analysis!.context.provenance,
            mode: "live",
            snapshot_hash: null,
          },
        },
      },
    };
    const api: ChangeSafeApi = {
      ...createGoldenApi(),
      getRun: vi.fn(async () => custom),
      subscribe: (_runId, after, onEvent) => {
        queueMicrotask(() => {
          for (const event of goldenEvents) {
            if (event.sequence > after) onEvent(event);
          }
        });
        return () => undefined;
      },
    };
    window.sessionStorage.setItem(
      RUN_SESSION_KEY,
      JSON.stringify({ runId: RUN_ID, lastSequence: 0 }),
    );

    render(<App api={api} />);

    expect(
      await screen.findByText("Live DataHub evidence · payments_daily"),
    ).toBeVisible();
    expect(
      screen.queryByText("Official DataHub showcase-ecommerce"),
    ).not.toBeInTheDocument();
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
    expect(screen.getAllByText("order_details").length).toBeGreaterThan(0);
    expect(screen.getAllByText("cust_email").length).toBeGreaterThan(0);
    expect(screen.getAllByText("primary_email").length).toBeGreaterThan(0);
    const findings = screen.getAllByTestId("impact-category");
    expect(findings).toHaveLength(6);
    expect(findings.every((finding) => finding.querySelector("article"))).toBe(true);
    expect(screen.getByText("Potentially high, not quantified")).toBeVisible();
    expect(screen.getAllByText("Customer Analytics Measures").length).toBeGreaterThan(0);
    expect(screen.getAllByTestId("lineage-flow")).toHaveLength(2);
    expect(screen.getAllByTestId("artifact-file")).toHaveLength(7);
    expect(screen.getByText("What this file does")).toBeVisible();
    expect(screen.getByText("Failure this prevents")).toBeVisible();
    expect(screen.getByText("12 / 12")).toBeVisible();
    expect(screen.getByText("Recorded DataHub evidence")).toBeVisible();
    expect(screen.getByText("Preview only")).toBeVisible();
    expect(screen.getByText(/^Completed in /)).toBeVisible();
    await user.click(screen.getByText("About this run"));
    expect(
      screen.getByText(
        "Same request + same evidence = same verified result.",
      ),
    ).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Approve preview" }),
    ).toBeEnabled();
    expect(document.body).not.toHaveTextContent(/judge/i);
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

  it("treats terminal event-stream closure as completion, not disconnection", async () => {
    const user = userEvent.setup();
    const created: RunView = {
      ...goldenRun,
      state: "created",
      analysis: null,
    };
    const completed: RunView = {
      ...goldenRun,
      state: "completed",
      publication: previewReceipt,
    };
    let current = created;
    let publicationStreamError: (() => void) | null = null;
    let releaseApproval: (() => void) | null = null;
    const api: ChangeSafeApi = {
      ...createGoldenApi(),
      createRun: vi.fn(async () => current),
      getRun: vi.fn(async () => current),
      approve: vi.fn(() => {
        current = { ...goldenRun, state: "preparing_preview" };
        return new Promise<PublicationReceipt>((resolve) => {
          releaseApproval = () => {
            current = completed;
            resolve(previewReceipt);
          };
        });
      }),
      subscribe: (_runId, after, onEvent, onError) => {
        if (current.state === "created") {
          queueMicrotask(() => {
            for (const event of goldenEvents) {
              if (event.sequence <= after) continue;
              if (event.state === "awaiting_approval") current = goldenRun;
              onEvent(event);
            }
          });
        } else {
          publicationStreamError = onError ?? null;
        }
        return () => undefined;
      },
    };

    render(<App api={api} />);
    await user.click(screen.getByRole("button", { name: "Analyze change" }));
    await user.click(
      await screen.findByRole("button", { name: "Approve preview" }),
    );
    await waitFor(() => expect(publicationStreamError).not.toBeNull());

    current = completed;
    await act(async () => {
      publicationStreamError?.();
      publicationStreamError?.();
    });
    expect(
      screen.queryByText("Live progress disconnected. Refresh to resume this run."),
    ).not.toBeInTheDocument();
    await act(async () => releaseApproval?.());

    expect(await screen.findByText("Preview ready")).toBeVisible();
    expect(
      screen.queryByText("Live progress disconnected. Refresh to resume this run."),
    ).not.toBeInTheDocument();
  });

  it("retries one confirmed nonterminal stream disconnect before reporting it", async () => {
    const user = userEvent.setup();
    const created: RunView = {
      ...goldenRun,
      state: "created",
      analysis: null,
    };
    const streamErrors: Array<() => void> = [];
    const api: ChangeSafeApi = {
      ...createGoldenApi(),
      createRun: vi.fn(async () => created),
      getRun: vi.fn(async () => created),
      subscribe: (_runId, _after, _onEvent, onError) => {
        if (onError) streamErrors.push(onError);
        return () => undefined;
      },
    };

    render(<App api={api} />);
    await user.click(screen.getByRole("button", { name: "Analyze change" }));
    await waitFor(() => expect(streamErrors).toHaveLength(1));

    await act(async () => streamErrors[0]?.());
    await waitFor(() => expect(streamErrors).toHaveLength(2));
    expect(
      screen.queryByText("Live progress disconnected. Refresh to resume this run."),
    ).not.toBeInTheDocument();

    await act(async () => streamErrors[1]?.());
    expect(
      await screen.findByText(
        "Live progress disconnected. Refresh to resume this run.",
      ),
    ).toBeVisible();
  });

  it("trusts a completed receipt when the approval response is lost", async () => {
    const user = userEvent.setup();
    let approvalAttempted = false;
    const completed: RunView = {
      ...goldenRun,
      state: "completed",
      publication: previewReceipt,
    };
    const api: ChangeSafeApi = {
      ...createGoldenApi(),
      getRun: vi.fn(async () => (approvalAttempted ? completed : goldenRun)),
      approve: vi.fn(async () => {
        approvalAttempted = true;
        throw new Error("The approval response was interrupted.");
      }),
    };

    render(<App api={api} />);
    await user.click(screen.getByRole("button", { name: "Analyze change" }));
    await user.click(
      await screen.findByRole("button", { name: "Approve preview" }),
    );

    expect(await screen.findByText("Preview ready")).toBeVisible();
    expect(
      screen.queryByText("The approval response was interrupted."),
    ).not.toBeInTheDocument();
  });

  it("follows persisted publication events while approval is still running", async () => {
    const user = userEvent.setup();
    const liveAnalysis: RunView = {
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
    const liveReceipt = {
      ...previewReceipt,
      mode: "live" as const,
      writeback: {
        ...previewReceipt.writeback,
        mode: "live" as const,
        label: "WRITTEN TO DATAHUB",
      },
    };
    let current: RunView = { ...liveAnalysis, state: "created", analysis: null };
    let publishEvent: ((event: RunEvent) => void) | null = null;
    let releaseApproval: (() => void) | null = null;
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
      getSchemaCatalog: vi.fn(async () => goldenSchemaCatalog),
      getOwnerActivity: vi.fn(async () => []),
      createRun: vi.fn(async () => current),
      getRun: vi.fn(async () => current),
      continueWithSnapshot: vi.fn(async () => current),
      approve: vi.fn(
        () =>
          new Promise<PublicationReceipt>((resolve) => {
            releaseApproval = () => {
              current = {
                ...liveAnalysis,
                state: "completed",
                publication: liveReceipt,
              };
              publishEvent?.({
                ...goldenEvents.at(-1)!,
                sequence: 8,
                state: "completed",
                public_message: "Publication complete",
              });
              resolve(liveReceipt);
            };
          }),
      ),
      subscribe: (_runId, after, onEvent) => {
        if (current.state === "created") {
          queueMicrotask(() => {
            for (const event of goldenEvents) {
              if (event.sequence <= after) continue;
              if (event.state === "awaiting_approval") current = liveAnalysis;
              onEvent(event);
            }
          });
        } else {
          publishEvent = onEvent;
          queueMicrotask(() => {
            current = { ...liveAnalysis, state: "publishing" };
            onEvent({
              ...goldenEvents.at(-1)!,
              sequence: 7,
              state: "publishing",
              public_message: "Publishing verified artifacts",
            });
          });
        }
        return () => undefined;
      },
    };

    render(<App api={api} />);
    await user.click(screen.getByRole("button", { name: "Analyze change" }));
    await user.click(
      await screen.findByRole("button", { name: "Publish approved change" }),
    );

    expect(await screen.findByText("Publishing approved change")).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Publishing…" }),
    ).toBeDisabled();

    await act(async () => releaseApproval?.());
    expect(await screen.findByText("Publication complete")).toBeVisible();
  });

  it("lets a verifier-blocked analysis return to an editable request", async () => {
    const user = userEvent.setup();
    const failed: RunView = {
      ...goldenRun,
      state: "failed",
      analysis: {
        ...goldenRun.analysis!,
        publication_eligible: false,
        validation: {
          passed: false,
          checks: goldenRun.analysis!.validation.checks.map((check, index) =>
            index === 0 ? { ...check, passed: false } : check,
          ),
        },
      },
      error: {
        code: "VERIFICATION_FAILED",
        message: "Generated artifacts did not pass every blocking check.",
        retryable: false,
      },
    };
    const api: ChangeSafeApi = {
      ...createGoldenApi(),
      getRun: vi.fn(async () => failed),
      subscribe: (_runId, after, onEvent) => {
        queueMicrotask(() => {
          for (const event of goldenEvents) {
            if (event.sequence > after) onEvent(event);
          }
          onEvent({
            ...goldenEvents.at(-1)!,
            sequence: 7,
            state: "failed",
            public_message: "Generated artifacts failed verification",
          });
        });
        return () => undefined;
      },
    };
    window.sessionStorage.setItem(
      RUN_SESSION_KEY,
      JSON.stringify({ runId: RUN_ID, lastSequence: 0 }),
    );

    render(<App api={api} />);

    expect(await screen.findByText("Change package blocked")).toBeVisible();
    expect(screen.getByText("11 / 12")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "New analysis" }));
    expect(
      screen.getByRole("button", { name: "Analyze change" }),
    ).toBeEnabled();
  });

  it("clears a traced impact before a new analysis", async () => {
    const user = userEvent.setup();
    render(<App api={createGoldenApi()} />);
    await user.click(screen.getByRole("button", { name: "Analyze change" }));

    const trace = await screen.findByRole("button", {
      name: "Trace supporting evidence for Data integrity",
    });
    await user.click(trace);
    expect(trace).toHaveAttribute("aria-expanded", "true");

    await user.click(screen.getByRole("button", { name: "Approve preview" }));
    await user.click(await screen.findByRole("button", { name: "New analysis" }));
    await user.click(screen.getByRole("button", { name: "Analyze change" }));

    expect(
      await screen.findByRole("button", {
        name: "Trace supporting evidence for Data integrity",
      }),
    ).toHaveAttribute("aria-expanded", "false");
  });

  it("renders generated code as text rather than injected HTML", async () => {
    const user = userEvent.setup();
    const api = createGoldenApi();
    render(<App api={api} />);
    await user.click(screen.getByRole("button", { name: "Analyze change" }));

    expect(await screen.findByText(/cust_email as primary_email/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "PR_BODY.md" }));
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
      getSchemaCatalog: vi.fn(async () => goldenSchemaCatalog),
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
    expect(
      screen.getByRole("heading", { name: "Live DataHub is unavailable" }),
    ).toBeVisible();
    expect(
      screen.getByText("Preview only"),
    ).toBeVisible();
    expect(
      screen.getByText("Reading the existing data contract").closest("li"),
    ).toHaveTextContent("Interrupted");
    expect(continueWithSnapshot).not.toHaveBeenCalled();

    await user.click(confirm);

    expect(continueWithSnapshot).toHaveBeenCalledWith(RUN_ID);
  });

  it("lets a user start over after a fresh analysis failure", async () => {
    const user = userEvent.setup();
    const failed: RunView = {
      ...goldenRun,
      state: "failed",
      analysis: null,
      error: {
        code: "CONTEXT_LOAD_FAILED",
        message: "Metadata context could not be loaded.",
        retryable: false,
      },
    };
    const failedEvent: RunEvent = {
      run_id: RUN_ID,
      sequence: 2,
      state: "failed",
      public_message: "Metadata context could not be loaded",
      evidence: [],
      created_at: failed.updated_at,
    };
    const api: ChangeSafeApi = {
      ...createGoldenApi(),
      createRun: vi.fn(async () => failed),
      getRun: vi.fn(async () => failed),
      subscribe: (_runId, _after, onEvent) => {
        queueMicrotask(() => onEvent(failedEvent));
        return () => undefined;
      },
    };

    render(<App api={api} />);
    await user.click(screen.getByRole("button", { name: "Analyze change" }));

    expect(
      await screen.findByText("Metadata context could not be loaded."),
    ).toBeVisible();
    await user.click(screen.getByRole("button", { name: "New analysis" }));
    expect(
      screen.getByRole("button", { name: "Analyze change" }),
    ).toBeEnabled();
  });

  it("lets a restored failed run return to the editable form", async () => {
    const user = userEvent.setup();
    const failed: RunView = {
      ...goldenRun,
      state: "failed",
      analysis: null,
      error: {
        code: "CONTEXT_LOAD_FAILED",
        message: "The saved metadata read stopped safely.",
        retryable: false,
      },
    };
    const failedEvent: RunEvent = {
      run_id: RUN_ID,
      sequence: 2,
      state: "failed",
      public_message: "The saved metadata read stopped safely",
      evidence: [],
      created_at: failed.updated_at,
    };
    const api: ChangeSafeApi = {
      ...createGoldenApi(),
      getRun: vi.fn(async () => failed),
      subscribe: (_runId, _after, onEvent) => {
        queueMicrotask(() => onEvent(failedEvent));
        return () => undefined;
      },
    };
    window.sessionStorage.setItem(
      RUN_SESSION_KEY,
      JSON.stringify({ runId: RUN_ID, lastSequence: 2 }),
    );

    render(<App api={api} />);

    expect(
      await screen.findByText("The saved metadata read stopped safely."),
    ).toBeVisible();
    await user.click(screen.getByRole("button", { name: "New analysis" }));
    expect(
      screen.getByRole("button", { name: "Analyze change" }),
    ).toBeEnabled();
  });
});
