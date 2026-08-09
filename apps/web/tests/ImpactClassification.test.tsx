import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ImpactClassification } from "../src/components/ImpactClassification";
import { goldenRun } from "./fixtures";

describe("ImpactClassification", () => {
  it("renders evidence findings with an explicit trace action", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    const impacts = goldenRun.analysis?.impacts ?? [];

    render(
      <ImpactClassification impacts={impacts} onSelect={onSelect} selected={null} />,
    );

    expect(screen.getAllByTestId("impact-category")).toHaveLength(6);
    expect(screen.getByText("Potentially high, not quantified")).toBeVisible();
    expect(screen.getByText("Inferred evidence")).toBeVisible();
    expect(screen.getByText(impacts[4].summary)).toBeVisible();
    expect(screen.getByText(impacts[4].basis)).toBeVisible();

    const trace = screen.getByRole("button", {
      name: "Trace supporting evidence for Financial exposure",
    });
    expect(trace).toHaveAttribute("aria-expanded", "false");
    expect(trace).not.toHaveAttribute("aria-pressed");

    await user.click(trace);
    expect(onSelect).toHaveBeenCalledWith(impacts[4]);
  });

  it("keeps the finding stable and puts active state on a clear trace action", () => {
    const impacts = goldenRun.analysis?.impacts ?? [];

    render(
      <ImpactClassification
        impacts={impacts}
        onSelect={vi.fn()}
        selected={impacts[0]}
      />,
    );

    const finding = screen.getAllByTestId("impact-category")[0]
      .querySelector("article");
    const clear = screen.getByRole("button", {
      name: "Clear evidence trace for Data integrity",
    });

    expect(finding).not.toHaveClass("is-selected");
    expect(clear).toHaveAttribute("aria-expanded", "true");
    expect(clear).toHaveClass("is-active");
    expect(clear).toHaveTextContent("Clear evidence trace");
  });
});
