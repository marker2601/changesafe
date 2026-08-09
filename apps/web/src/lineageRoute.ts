import type { AffectedAsset, ContextBundle } from "./types";

export type RouteDirection = "upstream" | "downstream";

export interface FieldEndpoint {
  urn: string;
  name: string;
  field: string | null;
}

export interface LineageRoute {
  direction: RouteDirection;
  source: FieldEndpoint;
  destination: FieldEndpoint;
  degree: number | null;
  precision: AffectedAsset["lineage_precision"];
  orderedAssetPath: string[];
  limitation: string | null;
}

export function lineageDegree(asset: AffectedAsset): number | null {
  if (asset.lineage_degree !== null) return asset.lineage_degree;
  return asset.lineage_path.length >= 2 ? asset.lineage_path.length - 1 : null;
}

export function buildLineageRoute(
  context: ContextBundle,
  asset: AffectedAsset,
  direction: RouteDirection,
): LineageRoute {
  const target: FieldEndpoint = {
    urn: context.target_urn,
    name: context.target_name,
    field: context.field,
  };
  const endpoint: FieldEndpoint = {
    urn: asset.urn,
    name: asset.name,
    field: asset.field,
  };
  const degree = lineageDegree(asset);
  const source = direction === "upstream" ? endpoint : target;
  const destination = direction === "upstream" ? target : endpoint;
  const limitation =
    asset.lineage_precision === "dataset_level"
      ? `Dataset-level relationship; ${
          direction === "upstream" ? "source" : "destination"
        } field not returned by DataHub`
      : asset.lineage_precision === "endpoint_field" &&
          degree !== null &&
          degree > 1
        ? `${degree} hops; intermediate column mapping not returned by DataHub`
        : null;

  return {
    direction,
    source,
    destination,
    degree,
    precision: asset.lineage_precision,
    orderedAssetPath: asset.lineage_path,
    limitation,
  };
}

export function formatEndpoint(endpoint: FieldEndpoint): string {
  return endpoint.field === null
    ? endpoint.name
    : `${endpoint.name}.${endpoint.field}`;
}

export function formatRoute(route: LineageRoute): string {
  return `${formatEndpoint(route.source)} → ${formatEndpoint(route.destination)}`;
}
