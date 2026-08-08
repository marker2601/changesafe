import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Header } from "../src/components/Header";
import type { PublicConfig } from "../src/types";

function config(overrides: Partial<PublicConfig>): PublicConfig {
  return {
    mode: "replay",
    live_context_available: false,
    llm_available: false,
    github_publication_available: false,
    datahub_writeback_available: false,
    openai_model: "gpt-5.6-luna",
    ...overrides,
  };
}

describe("runtime mode header", () => {
  it("labels auto mode as replay when no live context is configured", () => {
    render(<Header config={config({ mode: "auto" })} />);

    expect(screen.getByText("Snapshot replay")).toBeVisible();
    expect(screen.getByText("No credentials required")).toBeVisible();
  });

  it("labels auto mode as live-ready when DataHub access is configured", () => {
    render(
      <Header
        config={config({ mode: "auto", live_context_available: true })}
      />,
    );

    expect(screen.getByText("Live DataHub")).toBeVisible();
    expect(screen.getByText("Owner-gated publishing")).toBeVisible();
  });
});
