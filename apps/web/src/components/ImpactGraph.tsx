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
  ContextBundle,
  ImpactAssessment,
} from "../types";
import { EvidenceDrawer } from "./EvidenceDrawer";

interface ImpactGraphProps {
  context: ContextBundle;
  activeImpact: ImpactAssessment | null;
  dataHubOrigin?: string | null;
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
}: ImpactGraphProps) {
  const [selectedAsset, setSelectedAsset] = useState<AffectedAsset | null>(null);
  const highlighted = new Set(activeImpact?.evidence_urns ?? []);
  return (
    <section className="dependency-panel" aria-labelledby="dependency-heading">
      <header className="dependency-heading">
        <div>
          <span>Live dependency evidence</span>
          <h2 id="dependency-heading">Tracing what depends on cust_email</h2>
          <p>
            We&apos;re finding the models, reports and teams that rely on this field
            before preparing the change.
          </p>
        </div>
        <strong>
          {context.provenance.mode === "live"
            ? "Live DataHub"
            : "Checksummed replay"}
        </strong>
      </header>

      <div className="dependency-map">
        <section className="asset-column upstream-column" aria-label="Upstream inputs">
          <h3>Upstream inputs</h3>
          {context.upstream_assets.map((asset) => {
            const Icon = assetIcon(asset);
            return (
              <button
                aria-label={`${asset.name}, ${pathLabel(asset)} evidence`}
                className={highlighted.has(asset.urn) ? "is-highlighted" : ""}
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

        <div className="map-direction" aria-hidden="true">
          <ArrowRight />
        </div>

        <article className="target-node">
          <span className="target-platform">dbt governed model</span>
          <Database aria-hidden="true" />
          <strong>{context.target_name}</strong>
          <small>{context.target_domain ?? "Data product model"}</small>
          <em>PII · Governed</em>
        </article>

        <div className="map-direction" aria-hidden="true">
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
                className={highlighted.has(asset.urn) ? "is-highlighted" : ""}
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
