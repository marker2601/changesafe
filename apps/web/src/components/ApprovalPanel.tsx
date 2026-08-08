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

  if (run.state === "completed" && run.publication) {
    const preview = run.publication.mode === "preview";
    return (
      <section className="approval-panel receipt-panel" aria-live="polite">
        <div className="receipt-heading">
          <span><Check aria-hidden="true" /></span>
          <div>
            <h2>{preview ? "Preview ready" : "Publication complete"}</h2>
            <strong>{run.publication.writeback.label}</strong>
          </div>
        </div>
        <p>
          {preview
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
      <section className="approval-panel failure-panel" aria-live="assertive">
        <h2>Publication needs attention</h2>
        <p>{run.error?.message ?? "A partial publication is ready to retry."}</p>
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
          disabled={busy || !retryable}
          onClick={() => void onApprove(adminToken || undefined)}
          type="button"
        >
          <RotateCcw aria-hidden="true" />
          {retryable ? "Retry missing step" : "Operator action required"}
        </button>
        {!retryable ? (
          <p>Retry is disabled until the configuration or conflict is resolved.</p>
        ) : null}
      </section>
    );
  }

  if (run.state === "publishing" || run.state === "preparing_preview") {
    const resumingLive = run.state === "publishing";
    return (
      <section className="approval-panel" aria-live="polite">
        <h2>Durable publication checkpoint</h2>
        <p>
          ChangeSafe can resume the saved publication without repeating completed
          steps.
        </p>
        {resumingLive ? (
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
          disabled={busy}
          onClick={() => void onApprove(adminToken || undefined)}
          type="button"
        >
          <RotateCcw aria-hidden="true" />
          {resumingLive ? "Resume publication" : "Resume preview"}
        </button>
      </section>
    );
  }

  const ready = run.state === "awaiting_approval";
  return (
    <section className="approval-panel" aria-labelledby="approval-heading">
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
        {ready
          ? "No changes will be applied until approved."
          : "Approval unlocks only after every blocking check passes."}
      </p>
    </section>
  );
}
