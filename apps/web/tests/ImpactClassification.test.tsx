import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ImpactClassification } from "../src/components/ImpactClassification";
import { goldenRun } from "./fixtures";

describe("ImpactClassification", () => {
  it("renders all evidence-led categories and exposes inferred confidence", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    const impacts = goldenRun.analysis?.impacts ?? [];

    render(
      <ImpactClassification impacts={impacts} onSelect={onSelect} selected={null} />,
    );

    expect(screen.getAllByTestId("impact-category")).toHaveLength(6);
    expect(screen.getByText("Potentially high, not quantified")).toBeVisible();
    expect(screen.getByText("Inferred evidence")).toBeVisible();
    await user.click(screen.getByRole("button", { name: /Financial exposure/ }));
    expect(onSelect).toHaveBeenCalledWith(impacts[4]);
  });
});
