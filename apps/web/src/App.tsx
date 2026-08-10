import { ArrowRight, Database, ShieldCheck } from "lucide-react";
import { useState } from "react";

import { browserApi } from "./api";
import {
  changeSummary,
  DEFAULT_CHANGE_DRAFT,
  isOfficialDataset,
} from "./changeDraft";
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
import { WarehouseValidationPanel } from "./components/WarehouseValidationPanel";
import { useRun } from "./hooks/useRun";
import { useSchemaCatalog } from "./hooks/useSchemaCatalog";
import type { ChangeSafeApi, ImpactAssessment, SchemaField } from "./types";
import { warehouseValidationClaim } from "./warehouseEvidence";

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
  const schema = useSchemaCatalog(api, draft.asset_urn);
  const [ownerActivityOpen, setOwnerActivityOpen] = useState(false);
  const analysis = run?.analysis;
  const timelinePublicationMode =
    run?.publication?.mode ??
    (run?.state === "preparing_preview"
      ? "preview"
      : run?.state === "publishing" || run?.state === "publication_failed"
        ? "live"
        : analysis?.context.provenance.mode === "snapshot"
          ? "preview"
          : analysis?.context.provenance.mode === "live" &&
              Boolean(
                config?.github_publication_available ||
                  config?.datahub_writeback_available,
              )
            ? "live"
            : null);
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
  const officialDataset = isOfficialDataset(displayedChange);
  const heroMetadataTruth = analysis
    ? analysis.context.provenance.mode === "live"
      ? "Live DataHub metadata checked"
      : "Recorded DataHub evidence checked"
    : schema.catalog
      ? schema.catalog.provenance.mode === "live"
        ? "Live DataHub schema"
        : "Recorded DataHub schema"
      : schema.loading
        ? "Loading DataHub schema"
        : "Schema unavailable";
  const warehouse = analysis?.warehouse_validation ?? null;
  const heroWarehouseTruth = warehouse
    ? warehouseValidationClaim(warehouse)
    : run?.state === "validating_warehouse"
      ? "Warehouse validation in progress"
      : "Production rows not queried";
  const resetAnalysis = () => {
    setSelectedImpact(null);
    reset();
  };
  const selectCurrentField = (selected: SchemaField) => {
    setDraft((current) => ({
      ...current,
      field: selected.name,
      old_type: selected.data_type,
      new_field: current.field === selected.name ? current.new_field : "",
      new_type: current.field === selected.name ? current.new_type : "",
    }));
  };

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
          <div className="hero-truth-row" aria-label="Evidence status for this view">
            <span>
              <ShieldCheck aria-hidden="true" />
              {heroMetadataTruth}
            </span>
            <span>
              <Database aria-hidden="true" />
              {heroWarehouseTruth}
            </span>
          </div>
        </div>
        <RunProvenance config={config} events={events} run={run} />
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
              context={analysis?.context ?? null}
              mode={config?.mode}
              onCurrentFieldChange={selectCurrentField}
              schema={schema}
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
            ) : run?.state === "failed" ? (
              <div className="analysis-stage failure-stage">
                <ShieldCheck aria-hidden="true" />
                <span>Analysis stopped safely</span>
                <h2>No change was prepared</h2>
                <p>
                  {run.error?.message ??
                    "The analysis ended before a verified change package was created."}
                </p>
                <button
                  className="button button-primary"
                  onClick={resetAnalysis}
                  type="button"
                >
                  New analysis
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
              <section aria-label="Change preview" className="scenario-ready">
                <span>Ready to trace this change</span>
                <Database aria-hidden="true" />
                <h2>{officialDataset ? "order_details" : "Context not loaded"}</h2>
                <p>{changeSummary(displayedChange)}</p>
                <div>
                  <span>
                    {officialDataset
                      ? "Official ecommerce evidence"
                      : "Dataset facts pending"}
                  </span>
                  <ArrowRight aria-hidden="true" />
                  <span>Safe migration proof</span>
                </div>
              </section>
            )}
          </section>

          <LiveProcess
            events={events}
            field={displayedChange.field}
            publicationMode={timelinePublicationMode}
            runState={run?.state ?? null}
            warehouseValidation={warehouse}
            warehouseValidationRequired={Boolean(
              config?.warehouse_validation_required,
            )}
          />
        </div>

        <CommandRail
          artifactCount={analysis ? Object.keys(analysis.artifacts.files).length : 0}
          passedChecks={blocking.filter((check) => check.passed).length}
          runState={run?.state ?? null}
          totalChecks={blocking.length}
          warehouseValidation={warehouse}
        />

        {analysis ? (
          <section
            className="delivery-workspace"
            aria-label="Verified change package"
          >
            <ArtifactExplorer key={run.run_id} artifacts={analysis.artifacts} />
            <aside className="governance-rail">
              <ValidationPanel validation={analysis.validation} />
              <WarehouseValidationPanel
                validation={analysis.warehouse_validation}
              />
              <ApprovalPanel
                busy={busy}
                config={config}
                onApprove={approve}
                onReset={resetAnalysis}
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
