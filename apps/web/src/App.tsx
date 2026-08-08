import { ArrowRight, ShieldCheck } from "lucide-react";

import { browserApi } from "./api";
import { ApprovalPanel } from "./components/ApprovalPanel";
import { ArtifactExplorer } from "./components/ArtifactExplorer";
import { ChangeForm } from "./components/ChangeForm";
import { Header } from "./components/Header";
import { ImpactGraph } from "./components/ImpactGraph";
import { RiskCard } from "./components/RiskCard";
import { RunTimeline } from "./components/RunTimeline";
import { ValidationPanel } from "./components/ValidationPanel";
import { useRun } from "./hooks/useRun";
import type { ChangeRequest, ChangeSafeApi } from "./types";

interface AppProps {
  api?: ChangeSafeApi;
}

function transitionLabel(change: ChangeRequest): string {
  if (change.operation === "rename") {
    return `${change.field} → ${change.new_field ?? "new field"}`;
  }
  if (change.operation === "type_change") {
    return `${change.field}: ${change.old_type ?? "current"} → ${change.new_type ?? "new"}`;
  }
  return `Remove ${change.field}`;
}

export function App({ api = browserApi }: AppProps) {
  const { config, run, events, busy, error, analyze, approve, reset } = useRun(api);
  const patchUrl = run
    ? (api.patchUrl?.(run.run_id) ?? `/api/runs/${run.run_id}/publication.patch`)
    : "#";

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Skip to analysis
      </a>
      <Header config={config} />
      <main id="main-content">
        <div className="analysis-grid">
          <aside className="request-rail">
            <ChangeForm busy={busy} onSubmit={analyze} />
          </aside>

          <section className="analysis-canvas" aria-live="polite">
            {error ? (
              <div className="global-error" role="alert">
                <strong>ChangeSafe stopped safely</strong>
                <span>{error}</span>
              </div>
            ) : null}
            {run ? (
              <>
                <header className="analysis-heading">
                  <span>Change analysis</span>
                  <h1>{transitionLabel(run.request)}</h1>
                </header>
                {run.analysis ? (
                  <>
                    <RiskCard risk={run.analysis.risk} />
                    <ImpactGraph context={run.analysis.context} />
                  </>
                ) : (
                  <div className="analysis-stage">
                    <span className="stage-mark">
                      <ShieldCheck aria-hidden="true" />
                    </span>
                    <h2>Gathering governed context</h2>
                    <p>
                      {events.at(-1)?.public_message ??
                        "The run is queued and waiting for its first evidence event."}
                    </p>
                  </div>
                )}
              </>
            ) : (
              <div className="empty-state">
                <span>
                  <ShieldCheck aria-hidden="true" />
                </span>
                <h1>Ready for change analysis</h1>
                <p>
                  Submit the seeded rename to inspect its real metadata blast radius,
                  safety score, and migration artifacts.
                </p>
                <ArrowRight aria-hidden="true" />
              </div>
            )}
          </section>

          <RunTimeline events={events} runState={run?.state ?? null} />
        </div>

        {run?.analysis ? (
          <div className="delivery-grid">
            <ArtifactExplorer key={run.run_id} artifacts={run.analysis.artifacts} />
            <aside className="governance-rail">
              <ValidationPanel validation={run.analysis.validation} />
              <ApprovalPanel
                busy={busy}
                config={config}
                onApprove={approve}
                onReset={reset}
                patchUrl={patchUrl}
                run={run}
              />
            </aside>
          </div>
        ) : null}
      </main>
      <footer className="app-footer">
        <span>Run ID: {run?.run_id.slice(0, 8) ?? "not started"}</span>
        <span>Environment: {config?.mode === "live" ? "LIVE" : "REPLAY"}</span>
        <span>
          Evidence adapter: {run?.analysis?.context.provenance.mode ?? "waiting"}
        </span>
      </footer>
    </div>
  );
}
