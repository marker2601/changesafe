import {
  CalendarClock,
  Check,
  Clock3,
  Copy,
  Database,
  GitPullRequestArrow,
  History,
} from "lucide-react";
import { useEffect, useState } from "react";

import { formatElapsed } from "../runTiming";
import type {
  PublicationReceipt,
  PublicConfig,
  RunEvent,
  RunState,
  RunView,
} from "../types";

interface RunProvenanceProps {
  config: PublicConfig | null;
  events?: RunEvent[];
  run: RunView | null;
}

const ACTIVE_ANALYSIS_STATES = new Set<RunState>([
  "created",
  "loading_context",
  "scoring_risk",
  "generating",
  "validating",
]);

const ANALYSIS_END_STATES = new Set<RunState>([
  "awaiting_approval",
  "context_fallback_required",
  "failed",
]);

function timestamp(value: string | undefined): number | null {
  if (!value) return null;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function formattedRetrieval(value: string): string {
  const parsed = timestamp(value);
  if (parsed === null) return value;
  return new Date(parsed)
    .toISOString()
    .replace("T", " ")
    .replace(/\.\d{3}Z$/, " UTC");
}

function durablePublicationMode(
  run: RunView | null,
  config: PublicConfig | null,
): PublicationReceipt["mode"] | null {
  if (run?.publication) return run.publication.mode;
  if (run?.state === "preparing_preview") return "preview";
  if (run?.state === "publishing" || run?.state === "publication_failed") {
    return "live";
  }
  if (run?.state === "completed") return null;

  const provenanceMode = run?.analysis?.context.provenance.mode;
  if (provenanceMode === "snapshot") return "preview";
  const externalPublication = Boolean(
    config?.github_publication_available || config?.datahub_writeback_available,
  );
  if (provenanceMode === "live") {
    return config === null ? null : externalPublication ? "live" : "preview";
  }
  if (config === null) return null;
  if (config.mode === "auto") return externalPublication ? null : "preview";
  return config.mode === "replay" || !externalPublication ? "preview" : "live";
}

function analysisEnd(events: RunEvent[]): number | null {
  const ordered = [...events].sort((left, right) => left.sequence - right.sequence);
  for (let index = ordered.length - 1; index >= 0; index -= 1) {
    const event = ordered[index];
    if (ANALYSIS_END_STATES.has(event.state)) return timestamp(event.created_at);
  }
  return null;
}

export function RunProvenance({
  config,
  events = [],
  run,
}: RunProvenanceProps) {
  const [now, setNow] = useState(() => Date.now());
  const [copied, setCopied] = useState(false);

  const analysisActive = Boolean(run && ACTIVE_ANALYSIS_STATES.has(run.state));
  const activeRunId = analysisActive ? run?.run_id : null;

  useEffect(() => {
    if (!activeRunId) return undefined;
    const timer = window.setInterval(() => setNow(Date.now()), 100);
    return () => window.clearInterval(timer);
  }, [activeRunId]);

  const provenance = run?.analysis?.context.provenance;
  const fallbackAttempted = Boolean(
    run?.state === "context_fallback_required" ||
      events.some((event) => event.state === "context_fallback_required"),
  );
  const replay = provenance?.mode === "snapshot";
  const publicationMode = durablePublicationMode(run, config);
  const start = timestamp(run?.created_at);
  const end = analysisActive
    ? now
    : (analysisEnd(events) ?? timestamp(run?.updated_at));
  const elapsed = start !== null && end !== null ? formatElapsed(end - start) : null;
  const snapshotHash = provenance?.snapshot_hash;
  const evidenceLabel =
    provenance?.mode === "live"
      ? "Live DataHub metadata"
      : replay && fallbackAttempted
        ? "Recorded evidence after live fallback"
        : replay
          ? "Recorded DataHub evidence"
          : fallbackAttempted
            ? "Live DataHub unavailable"
            : config === null
              ? "Loading configuration…"
              : config.mode === "replay"
                ? "Recorded DataHub evidence"
                : config.mode === "live"
                  ? "Live DataHub metadata"
                  : config.live_context_available
                    ? "Live DataHub when available"
                    : "Recorded fallback available";
  const publicationLabel =
    publicationMode === "live"
      ? "Owner-gated publishing"
      : publicationMode === "preview"
        ? "Preview only"
        : config === null
          ? "Loading configuration…"
          : run?.state === "completed"
            ? "Receipt unavailable"
            : fallbackAttempted
              ? "Awaiting fallback choice"
              : "Determined by this run";
  const evidenceId = snapshotHash
    ? `${snapshotHash.slice(0, 12)}…`
    : provenance?.mode === "live"
      ? "Live retrieval"
      : fallbackAttempted
        ? "Unavailable"
        : config === null
          ? "Loading…"
          : run
            ? "Not available yet"
            : "Not started";
  const retrievedLabel = provenance?.retrieved_at
    ? formattedRetrieval(provenance.retrieved_at)
    : fallbackAttempted
      ? "Not retrieved"
      : config === null
        ? "Loading…"
        : analysisActive
          ? "In progress"
          : run
            ? "Unavailable"
            : "Not started";
  const elapsedLabel = !run
    ? "Not started"
    : !elapsed
      ? "Unavailable"
      : analysisActive
        ? `Running for ${elapsed}`
        : run.state === "context_fallback_required"
          ? `Paused after ${elapsed}`
          : run.state === "failed"
            ? `Stopped after ${elapsed}`
            : `Completed in ${elapsed}`;
  const reproducibilityLabel = !run
    ? "Every completed run records its evidence identity."
    : replay
      ? "Same request + same evidence = same verified result."
      : provenance?.mode === "live"
        ? "Live metadata can change; retrieval time anchors this run's context."
        : "Evidence identity is recorded after metadata context is loaded.";

  const copyChecksum = async () => {
    if (!snapshotHash || !navigator.clipboard) return;
    await navigator.clipboard.writeText(snapshotHash);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1_200);
  };

  return (
    <section className="run-provenance" aria-label="Run facts">
      <dl>
        <div>
          <dt>
            {replay ? <History aria-hidden="true" /> : <Database aria-hidden="true" />}
            Evidence
          </dt>
          <dd>{evidenceLabel}</dd>
        </div>
        <div>
          <dt>
            <GitPullRequestArrow aria-hidden="true" />
            Publication
          </dt>
          <dd>{publicationLabel}</dd>
        </div>
        <div>
          <dt>
            <Clock3 aria-hidden="true" />
            Elapsed
          </dt>
          <dd>{elapsedLabel}</dd>
        </div>
        <div className="run-fact-evidence-id">
          <dt>Evidence ID</dt>
          <dd>
            <code title={snapshotHash ?? undefined}>{evidenceId}</code>
            {snapshotHash ? (
              <button
                aria-label="Copy full evidence checksum"
                onClick={() => void copyChecksum()}
                type="button"
              >
                {copied ? <Check aria-hidden="true" /> : <Copy aria-hidden="true" />}
              </button>
            ) : null}
          </dd>
        </div>
        <div>
          <dt>
            <CalendarClock aria-hidden="true" />
            Retrieved
          </dt>
          <dd>
            {provenance?.retrieved_at ? (
              <time dateTime={provenance.retrieved_at}>{retrievedLabel}</time>
            ) : (
              retrievedLabel
            )}
          </dd>
        </div>
      </dl>
      <p className="reproducibility-note">{reproducibilityLabel}</p>
      <details>
        <summary>About this run</summary>
        {config === null && !provenance ? (
          <p>
            Runtime configuration is loading. Evidence and publication mode are
            not inferred until it arrives.
          </p>
        ) : replay && fallbackAttempted ? (
          <p>
            A live DataHub read was attempted but could not complete. After
            confirmation, this run continued with checksum-verified recorded
            metadata; the preview performs no live writes.
          </p>
        ) : replay ? (
          <p>
            This run uses a checksum-verified recording of DataHub metadata. It
            makes the result reproducible and performs no live DataHub reads or
            writes.
          </p>
        ) : fallbackAttempted ? (
          <p>
            A live DataHub read was attempted but could not complete. The run is
            paused before any recorded fallback is used, and no writes have been
            made.
          </p>
        ) : provenance?.mode === "live" ? (
          <p>
            This run read current metadata from the configured DataHub service.
            External publication still requires explicit owner authorization.
          </p>
        ) : config?.mode === "replay" ? (
          <p>
            Runs use checksum-verified recorded DataHub metadata and remain in
            non-mutating preview mode.
          </p>
        ) : config?.mode === "auto" ? (
          <p>
            Each run attempts a live DataHub read first. If that read fails, the
            run pauses for confirmation before using recorded evidence.
          </p>
        ) : (
          <p>
            Runs read current metadata from the configured DataHub service.
            External publication still requires explicit owner authorization.
          </p>
        )}
      </details>
    </section>
  );
}
