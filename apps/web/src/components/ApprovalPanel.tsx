import {
  ArrowUpRight,
  Check,
  Download,
  FileSearch,
  LockKeyhole,
  RotateCcw,
} from "lucide-react";
import { useState } from "react";

import type { PublicConfig, RunView } from "../types";

interface ApprovalPanelProps {
  run: RunView;
  config: PublicConfig | null;
  busy: boolean;
  patchUrl: string;
  onApprove: (adminToken?: string) => void | Promise<void>;
  onReset: () => void;
}

export function ApprovalPanel({
  run,
  config,
  busy,
  patchUrl,
  onApprove,
  onReset,
}: ApprovalPanelProps) {
  const [adminToken, setAdminToken] = useState("");
  const livePublishing = Boolean(
    run.publication?.mode === "live" ||
      (run.analysis?.context.provenance.mode === "live" &&
        (config?.github_publication_available ||
          config?.datahub_writeback_available)),
  );
  const blockers = run.analysis?.approval_blockers ?? [];
  const firstBlocker = blockers[0]?.message ?? null;
  const publicationEligible = Boolean(
    run.analysis?.publication_eligible && blockers.length === 0,
  );

  if (run.state === "completed" && run.publication) {
    const preview = run.publication.mode === "preview";
    return (
      <section className="approval-panel receipt-panel" id="approval" aria-live="polite">
        <div className="receipt-heading">
          <span><Check aria-hidden="true" /></span>
          <div>
            <h2>{preview ? "Preview ready" : "Publication complete"}</h2>
            <strong>{run.publication.writeback.label}</strong>
          </div>
        </div>
        <p>
          {firstBlocker
            ? firstBlocker
            : preview
              ? "No external systems were changed."
              : "Verified artifacts and the decision receipt are published."}
        </p>
        <a className="button button-primary" download href={patchUrl}>
          <Download aria-hidden="true" />
          Download patch
        </a>
        {run.publication.pull_request_url ? (
          <a
            className="button button-secondary"
            href={run.publication.pull_request_url}
            rel="noreferrer"
            target="_blank"
          >
            <ArrowUpRight aria-hidden="true" />
            Open pull request
          </a>
        ) : (
          <a className="button button-secondary" href="#artifacts">
            <FileSearch aria-hidden="true" />
            Inspect artifacts
          </a>
        )}
        <button className="text-action" onClick={onReset} type="button">
          <RotateCcw aria-hidden="true" />
          New analysis
        </button>
      </section>
    );
  }

  if (run.state === "publication_failed") {
    const retryable = run.error?.retryable ?? false;
    return (
      <section className="approval-panel failure-panel" id="approval" aria-live="assertive">
        <h2>Publication needs attention</h2>
        <p>
          {firstBlocker ??
            run.error?.message ??
            "A partial publication is ready to retry."}
        </p>
        {run.publication?.pull_request_url ? (
          <a href={run.publication.pull_request_url}>The pull request was created</a>
        ) : null}
        {livePublishing && retryable ? (
          <label>
            Owner token
            <input
              autoComplete="off"
              onChange={(event) => setAdminToken(event.target.value)}
              type="password"
              value={adminToken}
            />
          </label>
        ) : null}
        <button
          className="button button-primary"
          disabled={busy || !retryable || !publicationEligible}
          onClick={() => void onApprove(adminToken || undefined)}
          type="button"
        >
          <RotateCcw aria-hidden="true" />
          {retryable ? "Retry missing step" : "Operator action required"}
        </button>
        {!retryable || !publicationEligible ? (
          <p>Retry is disabled until the configuration or conflict is resolved.</p>
        ) : null}
      </section>
    );
  }

  if (run.state === "failed") {
    return (
      <section
        className="approval-panel failure-panel"
        id="approval"
        aria-live="assertive"
      >
        <h2>Change package blocked</h2>
        <p>
          {firstBlocker ??
            run.error?.message ??
            "The generated change did not pass every blocking check."}
        </p>
        <p>The recorded validation evidence remains available for inspection.</p>
        <button className="button button-primary" onClick={onReset} type="button">
          <RotateCcw aria-hidden="true" />
          New analysis
        </button>
      </section>
    );
  }

  if (run.state === "publishing" || run.state === "preparing_preview") {
    const resumingLive = run.state === "publishing";
    const activeHeading = resumingLive
      ? "Publishing approved change"
      : "Preparing approved preview";
    return (
      <section className="approval-panel" id="approval" aria-live="polite">
        <h2>{busy ? activeHeading : "Durable publication checkpoint"}</h2>
        <p>
          {firstBlocker
            ? firstBlocker
            : busy
            ? "Persisted checkpoints update as each authorized step completes."
            : "ChangeSafe can resume the saved publication without repeating completed steps."}
        </p>
        {resumingLive && !busy ? (
          <label>
            Owner token
            <input
              autoComplete="off"
              onChange={(event) => setAdminToken(event.target.value)}
              type="password"
              value={adminToken}
            />
          </label>
        ) : null}
        <button
          className="button button-primary"
          disabled={busy || !publicationEligible}
          onClick={() => void onApprove(adminToken || undefined)}
          type="button"
        >
          <RotateCcw aria-hidden="true" />
          {busy
            ? resumingLive
              ? "Publishing…"
              : "Preparing preview…"
            : resumingLive
              ? "Resume publication"
              : "Resume preview"}
        </button>
      </section>
    );
  }

  const ready = run.state === "awaiting_approval" && publicationEligible;
  return (
    <section className="approval-panel" id="approval" aria-labelledby="approval-heading">
      <h2 id="approval-heading">Approval actions</h2>
      {livePublishing ? (
        <label>
          Owner token
          <input
            autoComplete="off"
            onChange={(event) => setAdminToken(event.target.value)}
            type="password"
            value={adminToken}
          />
        </label>
      ) : null}
      <button
        className="button button-primary"
        disabled={!ready || busy}
        onClick={() => void onApprove(adminToken || undefined)}
        type="button"
      >
        <Check aria-hidden="true" />
        {livePublishing ? "Publish approved change" : "Approve preview"}
      </button>
      <p className="approval-note">
        <LockKeyhole aria-hidden="true" />
        {firstBlocker ??
          (run.analysis && !run.analysis.publication_eligible
            ? "Approval is blocked by persisted policy."
            : ready
              ? "No changes will be applied until approved."
              : "Approval is unavailable for this persisted run state.")}
      </p>
    </section>
  );
}
