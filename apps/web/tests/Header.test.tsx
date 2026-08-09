import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Header } from "../src/components/Header";
import type { PublicConfig } from "../src/types";
import { goldenRun } from "./fixtures";

function config(overrides: Partial<PublicConfig>): PublicConfig {
  return {
    mode: "replay",
    live_context_available: false,
    datahub_ui_url: null,
    llm_available: false,
    github_publication_available: false,
    datahub_writeback_available: false,
    owner_activity_available: false,
    openai_model: "gpt-5.6-luna",
    ...overrides,
  };
}

describe("runtime mode header", () => {
  it("labels auto mode as replay when no live context is configured", () => {
    render(<Header config={config({ mode: "auto" })} run={null} />);

    expect(screen.getByText("Snapshot replay")).toBeVisible();
    expect(screen.getByText("Preview only / snapshot mode")).toBeVisible();
  });

  it("separates live context from disabled publication", () => {
    render(
      <Header
        config={config({ mode: "auto", live_context_available: true })}
        run={null}
      />,
    );

    expect(screen.getByText("Live DataHub")).toBeVisible();
    expect(
      screen.getByText("Preview only / publication disabled"),
    ).toBeVisible();
  });

  it("shows owner-gated publishing only when a live sink is enabled", () => {
    render(
      <Header
        config={config({
          mode: "auto",
          live_context_available: true,
          github_publication_available: true,
        })}
        run={null}
      />,
    );

    expect(screen.getByText("Owner-gated publishing")).toBeVisible();
  });

  it("keeps a restored publishing run labeled live during config drift", () => {
    render(
      <Header
        config={null}
        run={{ ...goldenRun, state: "publishing" }}
      />,
    );

    expect(screen.getByText("Owner-gated publishing")).toBeVisible();
  });

  it("offers private activity only when the owner capability is available", async () => {
    const user = userEvent.setup();
    const onOpenOwnerActivity = vi.fn();
    render(
      <Header
        config={config({ owner_activity_available: true })}
        onOpenOwnerActivity={onOpenOwnerActivity}
        run={null}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Owner activity" }));

    expect(onOpenOwnerActivity).toHaveBeenCalledOnce();
  });
});
