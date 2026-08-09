import { ArrowRight, Database, ShieldCheck } from "lucide-react";
import { useState } from "react";

import { browserApi } from "./api";
import { changeSummary, DEFAULT_CHANGE_DRAFT } from "./changeDraft";
import { ApprovalPanel } from "./components/ApprovalPanel";
import { ArtifactExplorer } from "./components/ArtifactExplorer";
import { ChangeForm } from "./components/ChangeForm";
import { CommandRail } from "./components/CommandRail";
import { Header } from "./components/Header";
import { ImpactClassification } from "./components/ImpactClassification";
import { ImpactGraph } from "./components/ImpactGraph";
import { LiveProcess } from "./components/LiveProcess";
import { OwnerActivity } from "./components/OwnerActivity";
import { RiskCard } from "./components/RiskCard";
import { RunProvenance } from "./components/RunProvenance";
import { ValidationPanel } from "./components/ValidationPanel";
import { useRun } from "./hooks/useRun";
import type { ChangeSafeApi, ImpactAssessment } from "./types";

interface AppProps {
  api?: ChangeSafeApi;
}

export function App({ api = browserApi }: AppProps) {
  const {
    config,
    run,
    events,
    busy,
    error,
    analyze,
    approve,
    continueWithSnapshot,
    reset,
  } = useRun(api);
  const [selectedImpact, setSelectedImpact] = useState<ImpactAssessment | null>(
    null,
  );
  const [draft, setDraft] = useState(DEFAULT_CHANGE_DRAFT);
  const [ownerActivityOpen, setOwnerActivityOpen] = useState(false);
  const analysis = run?.analysis;
  const activeImpact =
    analysis?.impacts.find(
      (impact) => impact.category === selectedImpact?.category,
    ) ?? null;
  const patchUrl = run
    ? (api.patchUrl?.(run.run_id) ?? `/api/runs/${run.run_id}/publication.patch`)
    : "#";
  const blocking =
    analysis?.validation.checks.filter((check) => check.blocking) ?? [];
  const displayedChange = run?.request ?? draft;

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Skip to analysis
      </a>
      <Header
        reviewActivityAvailable={Boolean(config?.owner_activity_available)}
        onOpenReviewActivity={() => setOwnerActivityOpen(true)}
      />
      {ownerActivityOpen ? (
        <OwnerActivity
          loadActivity={(token) => api.getOwnerActivity(token)}
          onClose={() => setOwnerActivityOpen(false)}
        />
      ) : null}

      <section className="product-hero">
        <div className="product-hero-copy">
          <span className="hero-kicker">Data contract change intelligence</span>
          <h1>Change data safely, with every dependency in view.</h1>
          <p>
            ChangeSafe uses DataHub evidence to find affected systems and teams,
            prepare a compatible migration, verify every generated file, and pause
            before anything is published.
          </p>
          <span className="official-badge">
            <ShieldCheck aria-hidden="true" />
            Official DataHub showcase-ecommerce
          </span>
        </div>
        <RunProvenance busy={busy} config={config} events={events} run={run} />
      </section>

      <main id="main-content">
        {error ? (
          <div className="global-error" role="alert">
            <ShieldCheck aria-hidden="true" />
            <span>
              <strong>ChangeSafe stopped safely</strong>
              {error}
            </span>
          </div>
        ) : null}

        <div className="command-center">
          <aside className="request-rail">
            <ChangeForm
              busy={busy}
              draft={draft}
              onDraftChange={setDraft}
              onSubmit={analyze}
              submittedRequest={run?.request ?? null}
            />
            {analysis ? (
              <>
                <ImpactClassification
                  impacts={analysis.impacts}
                  onSelect={(impact) =>
                    setSelectedImpact((current) =>
                      current?.category === impact.category ? null : impact,
                    )
                  }
                  selected={activeImpact}
                />
                <RiskCard risk={analysis.risk} />
              </>
            ) : (
              <section className="impact-placeholder" aria-label="Impact areas">
                <span>After context arrives</span>
                <strong>Six impact areas will be classified with evidence.</strong>
              </section>
            )}
          </aside>

          <section className="analysis-canvas" aria-live="polite">
            {analysis ? (
              <ImpactGraph
                activeImpact={activeImpact}
                context={analysis.context}
                dataHubOrigin={config?.datahub_ui_url}
                request={run.request}
              />
            ) : run?.state === "context_fallback_required" ? (
              <div className="analysis-stage fallback-stage">
                <ShieldCheck aria-hidden="true" />
                <span>Context decision required</span>
                <h2>Live DataHub is unavailable</h2>
                <p>
                  {run.error?.message ??
                    "Confirm the checksum-pinned replay before analysis continues."}
                </p>
                <button
                  className="button button-primary"
                  disabled={busy}
                  onClick={() => void continueWithSnapshot()}
                  type="button"
                >
                  Continue with labeled snapshot
                </button>
              </div>
            ) : run ? (
              <div className="analysis-stage">
                <Database aria-hidden="true" />
                <span>Analysis in progress</span>
                <h2>{events.at(-1)?.public_message ?? "Run accepted"}</h2>
                <p>
                  Real server events update this workspace as DataHub context,
                  generation, and verification complete.
                </p>
              </div>
            ) : (
              <div className="scenario-ready">
                <span>Ready to trace this change</span>
                <Database aria-hidden="true" />
                <h2>order_details</h2>
                <p>{changeSummary(displayedChange)}</p>
                <div>
                  <span>Order Entry Analytics</span>
                  <ArrowRight aria-hidden="true" />
                  <span>Safe migration proof</span>
                </div>
              </div>
            )}
          </section>

          <LiveProcess events={events} runState={run?.state ?? null} />
        </div>

        <CommandRail
          artifactCount={analysis ? Object.keys(analysis.artifacts.files).length : 0}
          passedChecks={blocking.filter((check) => check.passed).length}
          runState={run?.state ?? null}
          totalChecks={blocking.length}
        />

        {analysis ? (
          <section
            className="delivery-workspace"
            aria-label="Verified change package"
          >
            <ArtifactExplorer key={run.run_id} artifacts={analysis.artifacts} />
            <aside className="governance-rail">
              <ValidationPanel validation={analysis.validation} />
              <ApprovalPanel
                busy={busy}
                config={config}
                onApprove={approve}
                onReset={reset}
                patchUrl={patchUrl}
                run={run}
              />
            </aside>
          </section>
        ) : null}
      </main>

      <footer className="app-footer">
        <span>Run ID: {run?.run_id.slice(0, 8) ?? "not started"}</span>
        <span>
          Evidence source:{" "}
          {analysis?.context.provenance.mode === "live"
            ? "Live DataHub"
            : analysis
              ? "Recorded snapshot"
              : "Waiting"}
        </span>
        <span>
          Request: {displayedChange.operation} · {displayedChange.field}
        </span>
      </footer>
    </div>
  );
}
