import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RiskCard } from "../src/components/RiskCard";
import { goldenRun } from "./fixtures";

describe("RiskCard", () => {
  it("shows the deterministic score, band, and every evidence factor", () => {
    const analysis = goldenRun.analysis;
    if (!analysis) throw new Error("fixture analysis is required");

    render(<RiskCard risk={analysis.risk} />);

    expect(screen.getByText("90")).toBeVisible();
    expect(screen.getByText("Critical risk")).toBeVisible();
    expect(screen.getAllByTestId("risk-factor")).toHaveLength(6);
    expect(screen.getByText("Cross-domain impact")).toBeVisible();
  });
});
