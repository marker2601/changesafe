import { ChevronRight, Database, LayoutDashboard, Workflow } from "lucide-react";

import type { AffectedAsset } from "../types";

interface AffectedAssetsProps {
  assets: AffectedAsset[];
}

export function AffectedAssets({ assets }: AffectedAssetsProps) {
  return (
    <ol className="asset-nodes" aria-label="Downstream affected assets">
      {assets.map((asset) => {
        const Icon =
          asset.entity_type.toLowerCase() === "dashboard"
            ? LayoutDashboard
            : asset.is_production_ml
              ? Workflow
              : Database;
        return (
          <li data-testid="affected-asset-row" key={asset.urn}>
            <Icon aria-hidden="true" />
            <span>
              <strong>{asset.name}</strong>
              <small>{asset.domain ?? asset.entity_type}</small>
            </span>
            <ChevronRight aria-hidden="true" />
          </li>
        );
      })}
    </ol>
  );
}
