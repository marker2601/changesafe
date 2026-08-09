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

    render(<ArtifactExplorer artifacts={artifacts} />);

    expect(screen.getByText("What this file does")).toBeVisible();
    expect(screen.getByText("Failure this prevents")).toBeVisible();
    expect(screen.getByText("dbt model SQL")).toBeVisible();
    expect(screen.getByText(/breaking existing consumers/i)).toBeVisible();

    await user.click(
      screen.getByRole("tab", {
        name: /tests\/assert_cust_email_compatibility\.sql/,
      }),
    );

    expect(screen.getByText("Compatibility test")).toBeVisible();
    expect(screen.getByText(/premature removal/i)).toBeVisible();
    expect(
      screen.getByText(/select \* from order_details where cust_email/i),
    ).toBeVisible();
  });
});
