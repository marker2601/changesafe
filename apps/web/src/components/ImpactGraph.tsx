import {
  ArrowRight,
  BarChart3,
  Boxes,
  Database,
  PanelsTopLeft,
  Warehouse,
} from "lucide-react";
import { useState, type ComponentType } from "react";

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

function assetIcon(asset: AffectedAsset): ComponentType<{ "aria-hidden"?: boolean }> {
  const urn = asset.urn.toLowerCase();
  if (urn.includes("powerbi")) return BarChart3;
  if (urn.includes("looker")) return PanelsTopLeft;
  if (urn.includes("snowflake")) return Warehouse;
  return Boxes;
}

function pathLabel(asset: AffectedAsset): string {
  if (asset.lineage_path.length === 2) return "direct";
  if (asset.lineage_path.length > 2) return "multi-hop";
  return "relationship only";
}

function safeDataHubLink(origin: string | null | undefined, urn: string) {
  if (!origin) return null;
  return new URL(`/dataset/${encodeURIComponent(urn)}`, origin).toString();
}

export function ImpactGraph({
  context,
  activeImpact,
  dataHubOrigin,
  request,
}: ImpactGraphProps) {
  const [selectedAsset, setSelectedAsset] = useState<AffectedAsset | null>(null);
  const highlighted = new Set(activeImpact?.evidence_urns ?? []);
  const graphAssets = [...context.upstream_assets, ...context.downstream_assets];
  const highlightedAssetCount = graphAssets.filter((asset) =>
    highlighted.has(asset.urn),
  ).length;
  const dimUnrelated = activeImpact !== null && highlightedAssetCount > 0;
  const assetClassName = (asset: AffectedAsset) => {
    if (highlighted.has(asset.urn)) return "is-highlighted";
    return dimUnrelated ? "is-dimmed" : "";
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
          <h2 id="dependency-heading">
            Tracing what depends on {request.field}
          </h2>
          <p>
            DataHub evidence connects upstream inputs, this governed model, and
            every recorded dependent. The moving light shows relationship direction.
          </p>
        </div>
        <strong>
          {context.provenance.mode === "live"
            ? "Live DataHub"
            : "Checksummed replay"}
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
          {context.upstream_assets.map((asset) => {
            const Icon = assetIcon(asset);
            return (
              <button
                aria-label={`${asset.name}, ${pathLabel(asset)} evidence`}
                className={assetClassName(asset)}
                key={asset.urn}
                onClick={() => setSelectedAsset(asset)}
                type="button"
              >
                <Icon aria-hidden />
                <span>
                  <small>{asset.entity_type.replaceAll("_", " ")}</small>
                  <strong>{asset.name}</strong>
                  <em>{pathLabel(asset)}</em>
                </span>
              </button>
            );
          })}
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
          <strong>{context.target_name}</strong>
          <small>{context.target_domain ?? "Data product model"}</small>
          <em>PII · Governed</em>
        </article>

        <div className="lineage-flow" data-testid="lineage-flow" aria-hidden="true">
          <span className="lineage-flow-light" />
          <ArrowRight />
        </div>

        <section
          className="asset-column downstream-column"
          aria-label="Recorded dependents"
        >
          <h3>Recorded dependents</h3>
          {context.downstream_assets.map((asset) => {
            const Icon = assetIcon(asset);
            return (
              <button
                aria-label={`${asset.name}, ${asset.entity_type}, ${pathLabel(asset)} evidence`}
                className={assetClassName(asset)}
                key={asset.urn}
                onClick={() => setSelectedAsset(asset)}
                type="button"
              >
                <Icon aria-hidden />
                <span>
                  <small>{asset.entity_type.replaceAll("_", " ")}</small>
                  <strong>{asset.name}</strong>
                  <em>{pathLabel(asset)}</em>
                </span>
              </button>
            );
          })}
        </section>
      </div>

      <details className="accessible-dependencies">
        <summary>Accessible dependency list</summary>
        <ul>
          {context.downstream_assets.map((asset) => (
            <li key={asset.urn}>
              <strong>{asset.name}</strong>
              <span>
                {asset.entity_type.replaceAll("_", " ")} · {pathLabel(asset)} ·
                field {asset.field ?? "not recorded"}
              </span>
            </li>
          ))}
        </ul>
      </details>

      <EvidenceDrawer
        asset={selectedAsset}
        dataHubUrl={
          selectedAsset
            ? safeDataHubLink(dataHubOrigin, selectedAsset.urn)
            : null
        }
        onClose={() => setSelectedAsset(null)}
      />
    </section>
  );
}
