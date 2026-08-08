import { Database } from "lucide-react";

import type { ContextBundle } from "../types";
import { AffectedAssets } from "./AffectedAssets";

interface ImpactGraphProps {
  context: ContextBundle;
}

export function ImpactGraph({ context }: ImpactGraphProps) {
  return (
    <section className="lineage-section" aria-labelledby="lineage-heading">
      <div className="section-heading inline-heading">
        <div>
          <h3 id="lineage-heading">Lineage</h3>
          <p>
            {context.target_name} is upstream of {context.downstream_assets.length}{" "}
            assets
          </p>
        </div>
        <span className="evidence-source">
          {context.provenance.mode === "snapshot"
            ? "Checksummed snapshot"
            : "Live DataHub evidence"}
        </span>
      </div>
      <div className="lineage-canvas">
        <div className="source-node">
          <Database aria-hidden="true" />
          <span>
            <strong>{context.target_name}</strong>
            <small>{context.target_domain ?? "Dataset"}</small>
          </span>
        </div>
        <svg
          aria-hidden="true"
          className="lineage-connectors"
          preserveAspectRatio="none"
          viewBox="0 0 220 300"
        >
          <path d="M0 150 C90 150 80 36 220 36" />
          <path d="M0 150 C90 150 92 112 220 112" />
          <path d="M0 150 C90 150 92 188 220 188" />
          <path d="M0 150 C90 150 80 264 220 264" />
          <circle cx="2" cy="150" r="5" />
        </svg>
        <AffectedAssets assets={context.downstream_assets} />
      </div>
    </section>
  );
}
