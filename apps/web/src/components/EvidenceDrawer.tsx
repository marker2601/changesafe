import { ExternalLink, Route, X } from "lucide-react";
import { useEffect, useRef } from "react";

import { lineageKind } from "../lineageEvidence";
import type { AffectedAsset } from "../types";

interface EvidenceDrawerProps {
  asset: AffectedAsset | null;
  onClose: () => void;
  dataHubUrl?: string | null;
}

function evidenceLabel(asset: AffectedAsset): string {
  const kind = lineageKind(asset);
  if (asset.lineage_path.length > 0) {
    return kind === "direct" ? "Direct field evidence" : "Multi-hop field evidence";
  }
  if (asset.lineage_degree !== null) {
    const hops = asset.lineage_degree === 1 ? "1 hop" : `${asset.lineage_degree} hops`;
    return `${kind === "direct" ? "Direct" : "Multi-hop"} relationship evidence; ${hops} recorded, concrete path unavailable`;
  }
  return "Recorded relationship; path unavailable";
}

export function EvidenceDrawer({
  asset,
  onClose,
  dataHubUrl,
}: EvidenceDrawerProps) {
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (asset) closeRef.current?.focus();
  }, [asset]);

  if (!asset) return null;
  return (
    <div
      aria-label={`Evidence for ${asset.name}`}
      aria-modal="true"
      className="evidence-drawer"
      role="dialog"
    >
      <header>
        <span>DataHub evidence</span>
        <button
          aria-label="Close evidence"
          onClick={onClose}
          ref={closeRef}
          type="button"
        >
          <X aria-hidden="true" />
        </button>
      </header>
      <h3>{asset.name}</h3>
      <p className="evidence-kind">
        <Route aria-hidden="true" />
        {evidenceLabel(asset)}
      </p>
      <dl>
        <div>
          <dt>Type</dt>
          <dd>{asset.entity_type.replaceAll("_", " ")}</dd>
        </div>
        <div>
          <dt>Field</dt>
          <dd>{asset.field ?? "Not recorded"}</dd>
        </div>
        <div>
          <dt>Domain</dt>
          <dd>{asset.domain ?? "Not assigned"}</dd>
        </div>
      </dl>
      <div className="urn-block">
        <span>Entity URN</span>
        <code>{asset.urn}</code>
      </div>
      {asset.lineage_path.length ? (
        <ol className="evidence-path" aria-label="Recorded lineage path">
          {asset.lineage_path.map((urn, index) => (
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
