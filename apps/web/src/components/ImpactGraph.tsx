import {
  ArrowRight,
  BarChart3,
  Boxes,
  Database,
  PanelsTopLeft,
  Warehouse,
} from "lucide-react";
import { useState, type ComponentType } from "react";

import { compactLineageLabel } from "../lineageEvidence";
import {
  buildLineageRoute,
  formatEndpoint,
  formatRoute,
  type LineageRoute,
  type RouteDirection,
} from "../lineageRoute";
import type {
  AffectedAsset,
  ChangeRequest,
  ContextBundle,
  ImpactAssessment,
} from "../types";
import { EvidenceDrawer } from "./EvidenceDrawer";

interface ImpactGraphProps {
  context: ContextBundle;
  activeImpact: ImpactAssessment | null;
  dataHubOrigin?: string | null;
  request: ChangeRequest;
}

interface RouteAsset {
  asset: AffectedAsset;
  direction: RouteDirection;
  route: LineageRoute;
}

function assetIcon(asset: AffectedAsset): ComponentType<{ "aria-hidden"?: boolean }> {
  const urn = asset.urn.toLowerCase();
  if (urn.includes("powerbi")) return BarChart3;
  if (urn.includes("looker")) return PanelsTopLeft;
  if (urn.includes("snowflake")) return Warehouse;
  return Boxes;
}

function safeDataHubLink(origin: string | null | undefined, urn: string) {
  if (!origin) return null;
  return new URL(`/dataset/${encodeURIComponent(urn)}`, origin).toString();
}

function fieldPolicyLabel(context: ContextBundle): string {
  if (context.field_tags.length > 0) {
    const rawName = context.field_tags[0].split(":").at(-1) ?? context.field_tags[0];
    const scopedName = rawName.split(".").at(-1) ?? rawName;
    const label = scopedName.replaceAll("_", " ").replaceAll("-", " ");
    return `${label} · Recorded ${context.field_tags.length === 1 ? "tag" : "tags"}`;
  }
  if (context.glossary_terms.length > 0) {
    return `${context.glossary_terms.length} glossary ${
      context.glossary_terms.length === 1 ? "term" : "terms"
    } recorded`;
  }
  return "No field policy recorded";
}

function degreeLabel(route: LineageRoute): string {
  if (route.degree === null) return "Degree not returned";
  return `${route.degree} ${route.degree === 1 ? "hop" : "hops"}`;
}

export function ImpactGraph({
  context,
  activeImpact,
  dataHubOrigin,
  request,
}: ImpactGraphProps) {
  const [selectedRoute, setSelectedRoute] = useState<RouteAsset | null>(null);
  const highlighted = new Set(activeImpact?.evidence_urns ?? []);
  const upstreamRoutes = context.upstream_assets.map((asset) => ({
    asset,
    direction: "upstream" as const,
    route: buildLineageRoute(context, asset, "upstream"),
  }));
  const downstreamRoutes = context.downstream_assets.map((asset) => ({
    asset,
    direction: "downstream" as const,
    route: buildLineageRoute(context, asset, "downstream"),
  }));
  const routeAssets = [...upstreamRoutes, ...downstreamRoutes];
  const highlightedAssetCount = routeAssets.filter(({ asset }) =>
    highlighted.has(asset.urn),
  ).length;
  const dimUnrelated = activeImpact !== null && highlightedAssetCount > 0;
  const assetClassName = (asset: AffectedAsset) => {
    if (highlighted.has(asset.urn)) return "is-highlighted";
    return dimUnrelated ? "is-dimmed" : "";
  };
  const renderAsset = ({ asset, route, direction }: RouteAsset) => {
    const Icon = assetIcon(asset);
    return (
      <button
        aria-label={`${formatRoute(route)}, ${compactLineageLabel(asset)} evidence`}
        className={assetClassName(asset)}
        key={`${direction}-${asset.urn}`}
        onClick={() => setSelectedRoute({ asset, route, direction })}
        type="button"
      >
        <Icon aria-hidden />
        <span>
          <small>{asset.entity_type.replaceAll("_", " ")}</small>
          <strong>{asset.name}</strong>
          <span className="field-route">{formatRoute(route)}</span>
          <small className="route-degree">{degreeLabel(route)}</small>
          {route.limitation ? <em>{route.limitation}</em> : null}
        </span>
      </button>
    );
  };

  return (
    <section className="dependency-panel" aria-labelledby="dependency-heading">
      <header className="dependency-heading">
        <div>
          <span>
            {context.provenance.mode === "live"
              ? "Live dependency evidence"
              : "Recorded dependency evidence"}
          </span>
          <h2 id="dependency-heading">Tracing what depends on {request.field}</h2>
          <p>
            DataHub evidence connects upstream inputs, this governed model, and
            every recorded dependent. The moving light shows relationship direction.
          </p>
        </div>
        <strong>
          {context.provenance.mode === "live" ? "Live DataHub" : "Checksummed replay"}
        </strong>
      </header>

      {activeImpact ? (
        <p className="active-impact-filter" aria-live="polite">
          <strong>Showing evidence for {activeImpact.label}</strong>
          <span>
            {highlightedAssetCount > 0
              ? `${highlightedAssetCount} matching graph ${
                  highlightedAssetCount === 1 ? "node is" : "nodes are"
                } highlighted.`
              : "Its supporting metadata is recorded outside the lineage nodes."}
          </span>
        </p>
      ) : null}

      <div className="dependency-map" id="dependency-evidence-map">
        <section className="asset-column upstream-column" aria-label="Upstream inputs">
          <h3>Upstream inputs</h3>
          {upstreamRoutes.length > 0 ? (
            upstreamRoutes.map(renderAsset)
          ) : (
            <p className="route-empty">No field-level upstream evidence returned</p>
          )}
        </section>

        <div className="lineage-flow" data-testid="lineage-flow" aria-hidden="true">
          <span className="lineage-flow-light" />
          <ArrowRight />
        </div>

        <article
          className={`target-node${
            highlighted.has(context.target_urn) ? " is-highlighted" : ""
          }`}
        >
          <span className="target-platform">dbt governed model</span>
          <Database aria-hidden="true" />
          <strong>{formatEndpoint({ urn: context.target_urn, name: context.target_name, field: context.field })}</strong>
          <small>{context.target_domain ?? "Data product model"}</small>
          <em>{fieldPolicyLabel(context)}</em>
        </article>

        <div className="lineage-flow" data-testid="lineage-flow" aria-hidden="true">
          <span className="lineage-flow-light" />
          <ArrowRight />
        </div>

        <section className="asset-column downstream-column" aria-label="Recorded dependents">
          <h3>Recorded dependents</h3>
          {downstreamRoutes.length > 0 ? (
            downstreamRoutes.map(renderAsset)
          ) : (
            <p className="route-empty">No recorded downstream field route</p>
          )}
        </section>
      </div>

      <details className="accessible-dependencies">
        <summary>Accessible dependency list</summary>
        <ul aria-label="All recorded dependencies">
          {routeAssets.map(({ asset, route, direction }) => {
            const dataHubUrl = safeDataHubLink(dataHubOrigin, asset.urn);
            return (
              <li key={`${direction}-${asset.urn}`}>
                <strong>{formatRoute(route)}</strong>
                <span>
                  {direction === "upstream" ? "Upstream" : "Downstream"} · {asset.entity_type.replaceAll("_", " ")} · {compactLineageLabel(asset)} · {degreeLabel(route)}
                  {asset.domain ? ` · domain ${asset.domain}` : ""}
                </span>
                {route.limitation ? <em>{route.limitation}</em> : null}
                {dataHubUrl ? (
                  <a
                    aria-label={`Open ${asset.name} in DataHub`}
                    href={dataHubUrl}
                    rel="noreferrer"
                    target="_blank"
                  >
                    Open in DataHub
                  </a>
                ) : null}
              </li>
            );
          })}
        </ul>
      </details>

      <EvidenceDrawer
        asset={selectedRoute?.asset ?? null}
        dataHubUrl={
          selectedRoute
            ? safeDataHubLink(dataHubOrigin, selectedRoute.asset.urn)
            : null
        }
        onClose={() => setSelectedRoute(null)}
        route={selectedRoute?.route ?? null}
      />
    </section>
  );
}
