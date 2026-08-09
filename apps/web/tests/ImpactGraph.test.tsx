import { render, screen, within } from "@testing-library/react";
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
        request={goldenRun.request}
      />,
    );

    expect(screen.getAllByTestId("lineage-flow")).toHaveLength(2);
    expect(
      screen.getByRole("heading", {
        name: "Tracing what depends on cust_email",
      }),
    ).toBeVisible();
    expect(screen.getByText("Showing evidence for Data integrity")).toBeVisible();

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
        request={goldenRun.request}
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

  it("uses recorded degree for multi-hop live evidence without inventing a path", async () => {
    const user = userEvent.setup();
    const analysis = goldenRun.analysis;
    if (!analysis) throw new Error("fixture analysis is required");
    const asset = analysis.context.downstream_assets[2];
    const context = {
      ...analysis.context,
      downstream_assets: [
        {
          ...asset,
          lineage_degree: 2,
          lineage_path: [],
        },
      ],
      provenance: {
        ...analysis.context.provenance,
        mode: "live" as const,
        snapshot_hash: null,
      },
    };
    render(
      <ImpactGraph
        activeImpact={null}
        context={context}
        request={goldenRun.request}
      />,
    );

    await user.click(
      screen.getByRole("button", {
        name: /Customer Analytics Measures.*multi-hop.*path unavailable/i,
      }),
    );

    expect(
      screen.getByText(/Multi-hop relationship evidence.*path unavailable/i),
    ).toBeVisible();
    expect(
      screen.queryByRole("list", { name: "Recorded lineage path" }),
    ).not.toBeInTheDocument();
  });

  it("makes the accessible list equivalent to both graph directions", async () => {
    const user = userEvent.setup();
    const analysis = goldenRun.analysis;
    if (!analysis) throw new Error("fixture analysis is required");
    render(
      <ImpactGraph
        activeImpact={null}
        context={analysis.context}
        dataHubOrigin="https://datahub.example.com"
        request={goldenRun.request}
      />,
    );

    await user.click(screen.getByText("Accessible dependency list"));
    const list = screen.getByRole("list", {
      name: "All recorded dependencies",
    });

    expect(within(list).getByText("stg_order_details")).toBeVisible();
    expect(
      within(list).getByText(
        "Upstream · dataset · direct · field cust_email · domain Data Platform Team",
      ),
    ).toBeVisible();
    expect(within(list).getByText("ORDER_DETAILS")).toBeVisible();
    expect(
      within(list).getByText(
        "Downstream · dataset · direct · field cust_email · domain Ecommerce Operations",
      ),
    ).toBeVisible();

    const links = within(list).getAllByRole("link");
    expect(links).toHaveLength(
      analysis.context.upstream_assets.length +
        analysis.context.downstream_assets.length,
    );
    expect(
      within(list).getByRole("link", {
        name: "Open stg_order_details in DataHub",
      }),
    ).toHaveAttribute(
      "href",
      `https://datahub.example.com/dataset/${encodeURIComponent(
        analysis.context.upstream_assets[0].urn,
      )}`,
    );
  });

  it("derives the target policy label from recorded field metadata", () => {
    const analysis = goldenRun.analysis;
    if (!analysis) throw new Error("fixture analysis is required");
    const context = {
      ...analysis.context,
      field_tags: ["urn:li:tag:Quality_Certified"],
      glossary_terms: [],
    };
    const { rerender } = render(
      <ImpactGraph
        activeImpact={null}
        context={context}
        request={goldenRun.request}
      />,
    );

    expect(screen.getByText("Quality Certified · Recorded tag")).toBeVisible();

    rerender(
      <ImpactGraph
        activeImpact={null}
        context={{ ...context, field_tags: [], glossary_terms: [] }}
        request={goldenRun.request}
      />,
    );

    expect(screen.getByText("No field policy recorded")).toBeVisible();
  });

  it("dims unrelated nodes only while an impact evidence filter is active", () => {
    const analysis = goldenRun.analysis;
    if (!analysis) throw new Error("fixture analysis is required");
    const { rerender } = render(
      <ImpactGraph
        activeImpact={analysis.impacts[4]}
        context={analysis.context}
        request={goldenRun.request}
      />,
    );

    expect(
      screen.getByRole("button", { name: /Customer Analytics Measures/ }),
    ).toHaveClass("is-highlighted");
    expect(
      screen.getByRole("button", {
        name: /^ORDER_DETAILS, dataset, direct evidence$/,
      }),
    ).toHaveClass("is-dimmed");

    rerender(
      <ImpactGraph
        activeImpact={null}
        context={analysis.context}
        request={goldenRun.request}
      />,
    );

    expect(document.querySelectorAll(".is-dimmed")).toHaveLength(0);
  });
});
