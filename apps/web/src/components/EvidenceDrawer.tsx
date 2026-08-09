import { ExternalLink, Route, X } from "lucide-react";
import { useCallback, useEffect, useRef, type RefObject } from "react";

import { formatEndpoint, formatRoute, type LineageRoute } from "../lineageRoute";
import type { AffectedAsset } from "../types";

interface EvidenceDrawerProps {
  asset: AffectedAsset | null;
  route: LineageRoute | null;
  onClose: () => void;
  dataHubUrl?: string | null;
  triggerRef: RefObject<HTMLButtonElement | null>;
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

function humanize(value: string): string {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function EvidenceDrawer({
  asset,
  route,
  onClose,
  dataHubUrl,
  triggerRef,
}: EvidenceDrawerProps) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const drawerRef = useRef<HTMLDivElement>(null);
  const closeDrawer = useCallback(() => {
    triggerRef.current?.focus();
    onClose();
  }, [onClose, triggerRef]);
  useEffect(() => {
    if (asset && route) closeRef.current?.focus();
  }, [asset, route, closeDrawer]);

  useEffect(() => {
    if (!asset || !route) return undefined;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        closeDrawer();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [asset, route, closeDrawer]);

  if (!asset || !route) return null;
  return (
    <div
      aria-label={`Evidence for ${asset.name}`}
      aria-modal="true"
      className="evidence-drawer"
      onKeyDown={(event) => {
        if (event.key !== "Tab") return;
        const focusable = Array.from(
          drawerRef.current?.querySelectorAll<HTMLElement>(
            'a[href], button:not([disabled])',
          ) ?? [],
        );
        if (focusable.length === 0) return;
        const first = focusable[0];
        const last = focusable.at(-1);
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last?.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }}
      ref={drawerRef}
      role="dialog"
    >
      <header>
        <span>DataHub evidence</span>
        <button aria-label="Close evidence" onClick={closeDrawer} ref={closeRef} type="button">
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
          <dd>{humanize(route.precision)}</dd>
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
          <dd>{humanize(asset.entity_type)}</dd>
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
