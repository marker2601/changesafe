import { ExternalLink, Route, X } from "lucide-react";
import { useEffect, useRef } from "react";

import { formatEndpoint, formatRoute, type LineageRoute } from "../lineageRoute";
import type { AffectedAsset } from "../types";

interface EvidenceDrawerProps {
  asset: AffectedAsset | null;
  route: LineageRoute | null;
  onClose: () => void;
  dataHubUrl?: string | null;
}

function evidenceLabel(route: LineageRoute): string {
  if (route.precision === "dataset_level") return "Dataset-level relationship evidence";
  if (route.degree === null) return "Field endpoint evidence; degree unavailable";
  const type = route.precision === "exact_field" ? "field" : "endpoint";
  return `${route.degree === 1 ? "Direct" : "Multi-hop"} ${type} evidence; ${route.degree} ${route.degree === 1 ? "hop" : "hops"} recorded`;
}

function rawField(field: string | null): string {
  return field ?? "Not returned by DataHub";
}

export function EvidenceDrawer({
  asset,
  route,
  onClose,
  dataHubUrl,
}: EvidenceDrawerProps) {
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (asset && route) closeRef.current?.focus();
  }, [asset, route]);

  if (!asset || !route) return null;
  return (
    <div
      aria-label={`Evidence for ${asset.name}`}
      aria-modal="true"
      className="evidence-drawer"
      role="dialog"
    >
      <header>
        <span>DataHub evidence</span>
        <button aria-label="Close evidence" onClick={onClose} ref={closeRef} type="button">
          <X aria-hidden="true" />
        </button>
      </header>
      <h3>{formatRoute(route)}</h3>
      <p className="evidence-kind">
        <Route aria-hidden="true" />
        {evidenceLabel(route)}
      </p>
      {route.limitation ? <p className="route-limitation">{route.limitation}</p> : null}
      <dl>
        <div>
          <dt>Source</dt>
          <dd>{formatEndpoint(route.source)}</dd>
        </div>
        <div>
          <dt>Destination</dt>
          <dd>{formatEndpoint(route.destination)}</dd>
        </div>
        <div>
          <dt>Precision</dt>
          <dd>{route.precision.replaceAll("_", " ")}</dd>
        </div>
        <div>
          <dt>Source field</dt>
          <dd className="raw-field">{rawField(route.source.field)}</dd>
        </div>
        <div>
          <dt>Destination field</dt>
          <dd className="raw-field">{rawField(route.destination.field)}</dd>
        </div>
        <div>
          <dt>Type</dt>
          <dd>{asset.entity_type.replaceAll("_", " ")}</dd>
        </div>
      </dl>
      <div className="urn-block">
        <span>Source URN</span>
        <code>{route.source.urn}</code>
      </div>
      <div className="urn-block">
        <span>Destination URN</span>
        <code>{route.destination.urn}</code>
      </div>
      {route.orderedAssetPath.length > 0 ? (
        <ol className="evidence-path" aria-label="Recorded lineage path">
          {route.orderedAssetPath.map((urn, index) => (
            <li key={`${urn}-${index}`}>
              <span>{index + 1}</span>
              <code>{urn}</code>
            </li>
          ))}
        </ol>
      ) : null}
      {dataHubUrl ? (
        <a href={dataHubUrl} rel="noreferrer" target="_blank">
          Open evidence in DataHub
          <ExternalLink aria-hidden="true" />
        </a>
      ) : (
        <p className="evidence-link-note">
          A catalog link appears only when the operator configures a safe DataHub
          UI origin.
        </p>
      )}
    </div>
  );
}
