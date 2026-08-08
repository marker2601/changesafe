import { History, ShieldCheck } from "lucide-react";

import type { PublicConfig, RunView } from "../types";

interface HeaderProps {
  config: PublicConfig | null;
  run: RunView | null;
}

export function Header({ config, run }: HeaderProps) {
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
        <ShieldCheck aria-hidden="true" strokeWidth={1.8} />
        <span>ChangeSafe</span>
      </a>
      <div className="environment-status" aria-label="Runtime mode">
        <span>
          <History aria-hidden="true" />
          {contextLabel}
        </span>
        <span>
          <ShieldCheck aria-hidden="true" />
          {publicationLabel}
        </span>
      </div>
    </header>
  );
}
