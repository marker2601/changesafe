import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { RiskCard } from "../src/components/RiskCard";
import { goldenRun } from "./fixtures";

describe("RiskCard", () => {
  it("shows the deterministic score, band, and every evidence factor", async () => {
    const user = userEvent.setup();
    const analysis = goldenRun.analysis;
    if (!analysis) throw new Error("fixture analysis is required");

    render(<RiskCard risk={analysis.risk} />);

    expect(screen.getByText("80")).toBeVisible();
    expect(screen.getByText("High technical risk")).toBeVisible();
    expect(screen.getAllByTestId("risk-factor")).toHaveLength(5);
    await user.click(screen.getByText("Evidence factor ledger"));
    expect(screen.getByText("Cross-domain impact")).toBeVisible();
  });
});
