import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { ArtifactExplorer } from "../src/components/ArtifactExplorer";
import { goldenRun } from "./fixtures";

describe("ArtifactExplorer", () => {
  it("explains each generated file without changing its exact source bytes", async () => {
    const user = userEvent.setup();
    const artifacts = goldenRun.analysis?.artifacts;
    if (!artifacts) throw new Error("fixture artifacts are required");

    render(
      <ArtifactExplorer
        artifacts={{
          ...artifacts,
          files: Object.fromEntries(Object.entries(artifacts.files).reverse()),
        }}
      />,
    );

    expect(screen.getByText("What this file does")).toBeVisible();
    expect(screen.getByText("Failure this prevents")).toBeVisible();
    expect(screen.getByText("dbt model SQL")).toBeVisible();
    expect(screen.getAllByText(/compatibility layer/i).length).toBeGreaterThan(0);

    const modelFile = screen.getByRole("button", {
      name: /models\/marts\/order_details__changesafe\.sql/,
    });
    const compatibilityFile = screen.getByRole("button", {
      name: /tests\/assert_cust_email_compatibility\.sql/,
    });
    expect(modelFile).toHaveAttribute("aria-pressed", "true");
    expect(compatibilityFile).toHaveAttribute("aria-pressed", "false");

    await user.click(compatibilityFile);

    expect(compatibilityFile).toHaveAttribute("aria-pressed", "true");
    expect(modelFile).toHaveAttribute("aria-pressed", "false");

    expect(screen.getByText("Compatibility test")).toBeVisible();
    expect(screen.getByText(/premature removal/i)).toBeVisible();
    expect(
      screen.getByText(/from \{\{ ref\('order_details__changesafe'\) \}\}/i),
    ).toBeVisible();
  });
});
