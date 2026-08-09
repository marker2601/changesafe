import type { AffectedAsset } from "./types";

export type LineageKind = "direct" | "multi-hop" | "relationship only";

export function lineageKind(asset: AffectedAsset): LineageKind {
  if (asset.lineage_path.length === 2) return "direct";
  if (asset.lineage_path.length > 2) return "multi-hop";
  if (asset.lineage_degree === 1) return "direct";
  if ((asset.lineage_degree ?? 0) > 1) return "multi-hop";
  return "relationship only";
}

export function compactLineageLabel(asset: AffectedAsset): string {
  const kind = lineageKind(asset);
  if (asset.lineage_path.length > 0 || asset.lineage_degree === null) {
    return kind;
  }
  const hops = asset.lineage_degree === 1 ? "1 hop" : `${asset.lineage_degree} hops`;
  return `${kind} (${hops}; path unavailable)`;
}
