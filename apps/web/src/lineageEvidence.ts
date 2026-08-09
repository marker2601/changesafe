import type { AffectedAsset } from "./types";
import { lineageDegree } from "./lineageRoute";

export { lineageDegree } from "./lineageRoute";

export type LineageKind = "direct" | "multi-hop" | "relationship only";

export function lineageKind(asset: AffectedAsset): LineageKind {
  if (asset.lineage_precision === "dataset_level") return "relationship only";
  const degree = lineageDegree(asset);
  if (degree !== null && degree > 1) return "multi-hop";
  if (degree === 1) return "direct";
  return "relationship only";
}

export function compactLineageLabel(asset: AffectedAsset): string {
  const degree = lineageDegree(asset);
  if (asset.lineage_precision === "dataset_level") {
    return "dataset-level relationship";
  }
  if (degree === null) return "field endpoint; degree unavailable";
  return degree === 1
    ? "direct field route (1 hop)"
    : `multi-hop field route (${degree} hops)`;
}
