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
    expect(
      screen.getByText("Multi-hop endpoint evidence; 2 hops recorded"),
    ).toBeVisible();
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

  it("uses entity-specific DataHub links and omits unsupported entities", async () => {
    const user = userEvent.setup();
    const analysis = goldenRun.analysis;
    if (!analysis) throw new Error("fixture analysis is required");
    const dashboard = {
      ...analysis.context.downstream_assets[0],
      urn: "urn:li:dashboard:(looker,orders)",
      name: "Orders dashboard",
      entity_type: "dashboard",
    };
    const unsupported = {
      ...analysis.context.downstream_assets[1],
      urn: "urn:li:mlModel:orders",
      name: "Unsupported model",
      entity_type: "ml_model",
    };
    render(
      <ImpactGraph
        activeImpact={null}
        context={{ ...analysis.context, downstream_assets: [dashboard, unsupported] }}
        dataHubOrigin="https://datahub.example.com"
        request={goldenRun.request}
      />,
    );

    await user.click(screen.getByText("Accessible dependency list"));
    expect(screen.getByRole("link", { name: "Open Orders dashboard in DataHub" })).toHaveAttribute(
      "href",
      `https://datahub.example.com/dashboard/${encodeURIComponent(dashboard.urn)}`,
    );
    expect(
      screen.queryByRole("link", { name: "Open Unsupported model in DataHub" }),
    ).not.toBeInTheDocument();
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
        name: /Customer Analytics Measures.*multi-hop/i,
      }),
    );

    expect(
      within(screen.getByRole("dialog", { name: /Evidence for/ })).getByText(
        "2 hops; intermediate column mapping not returned by DataHub",
      ),
    ).toBeVisible();
    expect(
      screen.queryByRole("list", { name: "Recorded lineage path" }),
    ).not.toBeInTheDocument();
  });

  it("keeps recorded multi-hop degree authoritative over an endpoint-only path", () => {
    const analysis = goldenRun.analysis;
    if (!analysis) throw new Error("fixture analysis is required");
    const asset = analysis.context.downstream_assets[0];
    const context = {
      ...analysis.context,
      downstream_assets: [
        {
          ...asset,
          lineage_degree: 2,
          lineage_path: [analysis.context.target_urn, asset.urn],
        },
      ],
    };

    render(
      <ImpactGraph
        activeImpact={null}
        context={context}
        request={goldenRun.request}
      />,
    );

    expect(
      screen.getByRole("button", {
        name: /ORDER_DETAILS.*multi-hop field route \(2 hops\) evidence/i,
      }),
    ).toBeVisible();
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

    expect(
      within(list).getByText(/stg_order_details\.cust_email.*order_details\.cust_email/),
    ).toBeVisible();
    expect(
      within(list).getByText(
        "Upstream · dataset · direct field route (1 hop) · 1 hop · domain Data Platform Team",
      ),
    ).toBeVisible();
    expect(
      within(list).getByText(/order_details\.cust_email.*ORDER_DETAILS\.cust_email/),
    ).toBeVisible();
    expect(
      within(list).getByText(
        "Downstream · dataset · direct field route (1 hop) · 1 hop · domain Ecommerce Operations",
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

  it("shows the same exact directional field routes in cards, the drawer, and the accessible list", async () => {
    const user = userEvent.setup();
    const analysis = goldenRun.analysis;
    if (!analysis) throw new Error("fixture analysis is required");
    const downstream = analysis.context.downstream_assets[0];
    const context = {
      ...analysis.context,
      upstream_assets: [analysis.context.upstream_assets[0]],
      downstream_assets: [
        downstream,
        {
          ...analysis.context.downstream_assets[2],
          lineage_degree: 2,
          lineage_path: [
            analysis.context.target_urn,
            "urn:li:dataset:intermediate",
            analysis.context.downstream_assets[2].urn,
          ],
          lineage_precision: "endpoint_field" as const,
        },
      ],
    };
    render(
      <ImpactGraph activeImpact={null} context={context} request={goldenRun.request} />,
    );

    expect(
      within(screen.getByRole("region", { name: "Upstream inputs" })).getByRole(
        "button",
        { name: /stg_order_details\.cust_email → order_details\.cust_email/ },
      ),
    ).toBeVisible();
    expect(
      within(screen.getByRole("region", { name: "Recorded dependents" })).getByRole(
        "button",
        { name: /order_details\.cust_email → ORDER_DETAILS\.cust_email/ },
      ),
    ).toBeVisible();
    expect(
      within(screen.getByRole("region", { name: "Recorded dependents" })).getByText(
        "2 hops; intermediate column mapping not returned by DataHub",
      ),
    ).toBeVisible();

    await user.click(screen.getByRole("button", { name: /Customer Analytics Measures/ }));
    expect(
      screen.getAllByText("2 hops; intermediate column mapping not returned by DataHub"),
    ).toHaveLength(3);
    expect(screen.getByText("Source field")).toBeVisible();
    expect(screen.getByText("Destination field")).toBeVisible();

    await user.click(screen.getByText("Accessible dependency list"));
    const list = screen.getByRole("list", { name: "All recorded dependencies" });
    expect(
      within(list).getByText("stg_order_details.cust_email → order_details.cust_email"),
    ).toBeVisible();
    expect(
      within(list).getByText("order_details.cust_email → ORDER_DETAILS.cust_email"),
    ).toBeVisible();
    expect(
      within(list).getByText("2 hops; intermediate column mapping not returned by DataHub"),
    ).toBeVisible();
  });

  it("uses structural route markup and returns focus to the trigger after escape", async () => {
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

    const trigger = screen.getByRole("button", {
      name: /order_details\.cust_email → ORDER_DETAILS\.cust_email/,
    });
    const route = trigger.querySelector(".field-route");
    if (!route) throw new Error("field route is required");
    expect(route.querySelector(".field-route-source")).toHaveTextContent(
      "order_details.cust_email",
    );
    expect(route.querySelector(".field-route-arrow")).toHaveAttribute("aria-hidden", "true");
    expect(route.querySelector(".field-route-destination")).toHaveTextContent(
      "ORDER_DETAILS.cust_email",
    );

    await user.click(trigger);
    const drawer = screen.getByRole("dialog", { name: /Evidence for ORDER_DETAILS/ });
    const close = within(drawer).getByRole("button", { name: "Close evidence" });
    expect(close).toHaveFocus();
    await user.tab();
    expect(within(drawer).getByRole("link", { name: "Open evidence in DataHub" })).toHaveFocus();
    await user.tab();
    expect(close).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(drawer).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it("does not fabricate a field suffix for dataset-level evidence and renders evidence-empty states", async () => {
    const user = userEvent.setup();
    const analysis = goldenRun.analysis;
    if (!analysis) throw new Error("fixture analysis is required");
    const context = {
      ...analysis.context,
      upstream_assets: [],
      downstream_assets: [
        {
          ...analysis.context.downstream_assets[0],
          name: "Order Details dashboard",
          field: null,
          lineage_precision: "dataset_level" as const,
          lineage_degree: 1,
          lineage_path: [],
        },
      ],
    };
    render(
      <ImpactGraph activeImpact={null} context={context} request={goldenRun.request} />,
    );

    expect(screen.getByText("No field-level upstream evidence returned")).toBeVisible();
    expect(screen.queryByText("No recorded downstream field route")).not.toBeInTheDocument();
    expect(screen.queryByText("Order Details dashboard.cust_email")).not.toBeInTheDocument();
    expect(
      screen.getAllByText("Dataset-level relationship; destination field not returned by DataHub"),
    ).toHaveLength(2);

    await user.click(screen.getByText("Accessible dependency list"));
    expect(
      screen.getAllByText("Dataset-level relationship; destination field not returned by DataHub"),
    ).toHaveLength(2);

    render(
      <ImpactGraph
        activeImpact={null}
        context={{ ...context, downstream_assets: [] }}
        request={goldenRun.request}
      />,
    );
    expect(screen.getByText("No recorded downstream field route")).toBeVisible();
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
        name: /ORDER_DETAILS\.cust_email, direct field route \(1 hop\) evidence$/,
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
