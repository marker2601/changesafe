import {
  Check,
  Clock3,
  Copy,
  Database,
  GitPullRequestArrow,
  History,
} from "lucide-react";
import { useEffect, useState } from "react";

import { formatElapsed } from "../runTiming";
import type { PublicConfig, RunEvent, RunView } from "../types";

interface RunProvenanceProps {
  busy: boolean;
  config: PublicConfig | null;
  events?: RunEvent[];
  run: RunView | null;
}

function timestamp(value: string | undefined): number | null {
  if (!value) return null;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function RunProvenance({
  busy,
  config,
  events = [],
  run,
}: RunProvenanceProps) {
  const [now, setNow] = useState(() => Date.now());
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!busy || !run) return undefined;
    const timer = window.setInterval(() => setNow(Date.now()), 100);
    return () => window.clearInterval(timer);
  }, [busy, run]);

  const provenance = run?.analysis?.context.provenance;
  const liveContextUnavailable = run?.state === "context_fallback_required";
  const replay = provenance
    ? provenance.mode === "snapshot"
    : !config || config.mode === "replay" || !config.live_context_available;
  const externalPublication = Boolean(
    config?.github_publication_available || config?.datahub_writeback_available,
  );
  const livePublication = Boolean(
    run?.state === "publishing" ||
      run?.publication?.mode === "live" ||
      (!replay && externalPublication),
  );
  const start = timestamp(run?.created_at);
  const analysisEndEvent = [...events]
    .reverse()
    .find((event) => event.state === "awaiting_approval");
  const end = busy
    ? now
    : (timestamp(analysisEndEvent?.created_at) ?? timestamp(run?.updated_at));
  const elapsed = start !== null && end !== null ? formatElapsed(end - start) : null;
  const snapshotHash = provenance?.snapshot_hash;
  const evidenceId = snapshotHash ? `${snapshotHash.slice(0, 12)}…` : "Pending";

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
          <dd>
            {liveContextUnavailable
              ? "Live DataHub unavailable"
              : replay
                ? "Recorded DataHub evidence"
                : "Live DataHub"}
          </dd>
        </div>
        <div>
          <dt>
            <GitPullRequestArrow aria-hidden="true" />
            Publication
          </dt>
          <dd>{livePublication ? "Owner-gated publishing" : "Preview only"}</dd>
        </div>
        <div>
          <dt>
            <Clock3 aria-hidden="true" />
            Elapsed
          </dt>
          <dd>
            {elapsed
              ? `${busy ? "Running for" : "Completed in"} ${elapsed}`
              : "Not started"}
          </dd>
        </div>
        <div>
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
      </dl>
      {run?.analysis && replay ? (
        <p className="reproducibility-note">
          Same request + same evidence = same verified result.
        </p>
      ) : null}
      <details>
        <summary>About this run</summary>
        {replay ? (
          <p>
            This run uses a checksum-verified recording of DataHub metadata. It
            makes the result reproducible and performs no live DataHub reads or
            writes.
          </p>
        ) : (
          <p>
            This run reads current metadata from the configured DataHub service.
            External publication still requires explicit owner authorization.
          </p>
        )}
      </details>
    </section>
  );
}
