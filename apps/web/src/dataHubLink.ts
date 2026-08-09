import type { AffectedAsset } from "./types";

const entityRoutes: Record<string, string> = {
  dataset: "dataset",
  dashboard: "dashboard",
  chart: "chart",
  dataJob: "datajob",
};

function dataHubEntityType(urn: string): string | null {
  const match = /^urn:li:([^:]+):/.exec(urn);
  return match?.[1] ?? null;
}

export function safeDataHubLink(
  origin: string | null | undefined,
  asset: Pick<AffectedAsset, "urn">,
): string | null {
  if (!origin) return null;
  const entityType = dataHubEntityType(asset.urn);
  const route = entityType ? entityRoutes[entityType] : undefined;
  if (!route) return null;

  try {
    const originUrl = new URL(origin);
    if (originUrl.protocol !== "https:" && originUrl.protocol !== "http:") {
      return null;
    }
    return new URL(`/${route}/${encodeURIComponent(asset.urn)}`, originUrl.origin).toString();
  } catch {
    return null;
  }
}
