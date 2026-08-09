import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { ImpactGraph } from "../src/components/ImpactGraph";
import { goldenRun } from "./fixtures";

describe("ImpactGraph", () => {
  it("opens real multi-hop evidence from a keyboard-operable node", async () => {
    const user = userEvent.setup();
    const analysis = goldenRun.analysis;
    if (!analysis) throw new Error("fixture analysis is required");
    render(
      <ImpactGraph
        activeImpact={analysis.impacts[0]}
        context={analysis.context}
      />,
    );

    const node = screen.getByRole("button", {
      name: /Customer Analytics Measures/,
    });
    node.focus();
    await user.keyboard("{Enter}");

    expect(screen.getByRole("dialog", { name: /Evidence for/ })).toBeVisible();
    expect(screen.getByText("Multi-hop field evidence")).toBeVisible();
    expect(
      screen.getAllByText(analysis.context.downstream_assets[2].urn).length,
    ).toBeGreaterThan(0);
    expect(screen.getByText("Accessible dependency list")).toBeVisible();
    expect(screen.getByText("Recorded dependency evidence")).toBeVisible();
    expect(
      screen.queryByRole("link", { name: "Open evidence in DataHub" }),
    ).not.toBeInTheDocument();
  });

  it("keeps configured DataHub links on the explicit catalog origin", async () => {
    const user = userEvent.setup();
    const analysis = goldenRun.analysis;
    if (!analysis) throw new Error("fixture analysis is required");
    render(
      <ImpactGraph
        activeImpact={analysis.impacts[0]}
        context={analysis.context}
        dataHubOrigin="https://datahub.example.com"
      />,
    );

    await user.click(
      screen.getByRole("button", { name: /Customer Analytics Measures/ }),
    );

    const link = screen.getByRole("link", { name: "Open evidence in DataHub" });
    expect(link).toHaveAttribute(
      "href",
      `https://datahub.example.com/dataset/${encodeURIComponent(
        analysis.context.downstream_assets[2].urn,
      )}`,
    );
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noreferrer");
  });
});
