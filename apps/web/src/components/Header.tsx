import { Activity, Database, History, Network, ShieldCheck } from "lucide-react";

import type { PublicConfig, RunView } from "../types";

interface HeaderProps {
  config: PublicConfig | null;
  onOpenOwnerActivity?: () => void;
  run: RunView | null;
}

export function Header({ config, onOpenOwnerActivity, run }: HeaderProps) {
  const provenance = run?.analysis?.context.provenance.mode;
  const fallbackRequired = run?.state === "context_fallback_required";
  const replay = provenance
    ? provenance === "snapshot"
    : !config || config.mode === "replay" || !config.live_context_available;
  const externalPublication = Boolean(
    config?.github_publication_available || config?.datahub_writeback_available,
  );
  const livePublication = Boolean(
    run?.state === "publishing" ||
      run?.publication?.mode === "live" ||
      (!replay && externalPublication),
  );
  const contextLabel = fallbackRequired
    ? "Live unavailable"
    : replay
      ? "Snapshot replay"
      : "Live DataHub";
  const publicationLabel = livePublication
    ? "Owner-gated publishing"
    : replay
      ? "Preview only / snapshot mode"
      : "Preview only / publication disabled";
  return (
    <header className="app-header">
      <a className="brand" href="#main-content" aria-label="ChangeSafe home">
        <span className="brand-mark">
          <Network aria-hidden="true" />
        </span>
        <span>ChangeSafe</span>
      </a>
      <div className="environment-status" aria-label="Runtime mode">
        <span>
          {replay ? <History aria-hidden="true" /> : <Database aria-hidden="true" />}
          {contextLabel}
        </span>
        <span>
          <ShieldCheck aria-hidden="true" />
          {publicationLabel}
        </span>
      </div>
      {config?.owner_activity_available && onOpenOwnerActivity ? (
        <button
          className="owner-activity-trigger"
          onClick={onOpenOwnerActivity}
          type="button"
        >
          <Activity aria-hidden="true" />
          Owner activity
        </button>
      ) : null}
    </header>
  );
}
