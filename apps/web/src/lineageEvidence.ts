import type { AffectedAsset } from "./types";

export type LineageKind = "direct" | "multi-hop" | "relationship only";

export function lineageDegree(asset: AffectedAsset): number | null {
  const pathDegree =
    asset.lineage_path.length >= 2 ? asset.lineage_path.length - 1 : null;
  if (asset.lineage_degree === null) return pathDegree;
  if (pathDegree === null) return asset.lineage_degree;
  return Math.max(asset.lineage_degree, pathDegree);
}

export function lineageKind(asset: AffectedAsset): LineageKind {
  const degree = lineageDegree(asset);
  if (degree !== null && degree > 1) return "multi-hop";
  if (degree === 1) return "direct";
  return "relationship only";
}

export function compactLineageLabel(asset: AffectedAsset): string {
  const kind = lineageKind(asset);
  const degree = lineageDegree(asset);
  if (degree === null) return kind;
  const hops = degree === 1 ? "1 hop" : `${degree} hops`;
  const availability = asset.lineage_path.length === 0 ? "; path unavailable" : "";
  return `${kind} (${hops}${availability})`;
}
