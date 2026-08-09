import { ArrowRight, Database, Network, Play, ShieldCheck } from "lucide-react";
import type { FormEvent } from "react";

import {
  changeSummary,
  draftToRequest,
  isOfficialScenario,
  sourceCommitForOperation,
  type ChangeDraft,
} from "../changeDraft";
import type { ChangeOperation, ChangeRequest, ContextBundle } from "../types";

interface ChangeFormProps {
  busy: boolean;
  draft: ChangeDraft;
  onDraftChange: (draft: ChangeDraft) => void;
  onSubmit: (change: ChangeRequest) => void | Promise<void>;
  submittedRequest?: ChangeRequest | null;
  context?: ContextBundle | null;
}

function platformLabel(targetUrn: string): string {
  const platform = /urn:li:dataPlatform:([^,)]+)/i.exec(targetUrn)?.[1];
  if (!platform) return "Platform not recorded";
  if (platform.toLowerCase() === "dbt") return "dbt";
  return `${platform.charAt(0).toUpperCase()}${platform.slice(1).toLowerCase()}`;
}

function fieldPolicy(context: ContextBundle): string {
  const policyEvidence = [...context.field_tags, ...context.glossary_terms];
  if (policyEvidence.length === 0) return "No field policy recorded";
  const joined = policyEvidence.join(" ").toLowerCase();
  const labels = [];
  if (joined.includes("pii") || joined.includes("personal")) labels.push("PII");
  labels.push("Governed");
  return labels.join(" · ");
}

export function ChangeForm({
  busy,
  draft,
  onDraftChange,
  onSubmit,
  submittedRequest = null,
  context = null,
}: ChangeFormProps) {
  const submitted = submittedRequest !== null;
  const displayed = submittedRequest ?? draft;
  const official = isOfficialScenario(displayed);
  const facts = context
    ? {
        dataset: context.target_name,
        policy: fieldPolicy(context),
        platform: platformLabel(context.target_urn),
      }
    : official
      ? { dataset: "order_details", policy: "PII · Governed", platform: "dbt" }
      : {
          dataset: "Pending DataHub context",
          policy: "Pending DataHub context",
          platform: "Pending DataHub context",
        };
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void onSubmit(draftToRequest(draft));
  };

  const changeOperation = (operation: ChangeOperation) => {
    onDraftChange({
      ...draft,
      operation,
      source_commit: sourceCommitForOperation(operation),
    });
  };

  const destination =
    displayed.operation === "rename"
      ? displayed.new_field
      : displayed.operation === "remove"
        ? "retain through phase one"
        : `${displayed.new_type} compatibility field`;

  return (
    <form
      aria-label={submitted ? "Submitted change summary" : undefined}
      className={`change-form${submitted ? " is-submitted" : ""}`}
      onSubmit={submit}
    >
      <header className="panel-heading">
        <span>
          {official
            ? "Official ecommerce scenario"
            : context
              ? "Evidence-backed change"
              : "Custom change request"}
        </span>
        <h2>Change summary</h2>
        <p>
          {submitted
            ? "This request is bound to the evidence and artifacts shown here."
            : changeSummary(draft)}
        </p>
      </header>

      {!submitted ? (
        <label>
          Operation
          <select
            value={draft.operation}
            onChange={(event) =>
              changeOperation(event.target.value as ChangeOperation)
            }
          >
            <option value="rename">Rename field</option>
            <option value="remove">Remove field</option>
            <option value="type_change">Change type</option>
          </select>
        </label>
      ) : null}

      <p className="change-route" aria-label="Proposed field transition">
        <strong>{displayed.field}</strong>
        <ArrowRight aria-hidden="true" />
        <strong>{destination}</strong>
      </p>

      {!submitted ? (
        <div className="rename-pair">
          <label>
            Current field
            <input
              required
              value={draft.field}
              onChange={(event) =>
                onDraftChange({ ...draft, field: event.target.value })
              }
            />
          </label>
          <ArrowRight aria-hidden="true" />
          {draft.operation === "rename" ? (
            <label>
              New field
              <input
                required
                value={draft.new_field}
                onChange={(event) =>
                  onDraftChange({ ...draft, new_field: event.target.value })
                }
              />
            </label>
          ) : (
            <span className="operation-destination">
              {draft.operation === "remove"
                ? "Retain temporarily"
                : `${draft.new_type} alias`}
            </span>
          )}
        </div>
      ) : null}

      {!submitted && draft.operation === "type_change" ? (
        <div className="field-pair">
          <label>
            Current type
            <input
              required
            value={draft.old_type}
            onChange={(event) =>
              onDraftChange({ ...draft, old_type: event.target.value })
            }
            />
          </label>
          <label>
            New type
            <input
              required
            value={draft.new_type}
            onChange={(event) =>
              onDraftChange({ ...draft, new_type: event.target.value })
            }
            />
          </label>
        </div>
      ) : null}

      {submitted ? (
        <p className="submitted-change-note">
          <ShieldCheck aria-hidden="true" />
          Request locked to this evidence set
        </p>
      ) : null}

      <dl className="scenario-facts">
        <div>
          <dt>
            <Database aria-hidden="true" /> Dataset
          </dt>
          <dd>{facts.dataset}</dd>
        </div>
        <div>
          <dt>
            <ShieldCheck aria-hidden="true" /> Field policy
          </dt>
          <dd>{facts.policy}</dd>
        </div>
        <div>
          <dt>
            <Network aria-hidden="true" /> Catalog platform
          </dt>
          <dd>{facts.platform}</dd>
        </div>
      </dl>

      {!submitted ? (
        <>
          <details className="advanced-change-fields">
            <summary>Advanced request fields</summary>
            <label>
              Dataset URN
              <input
                required
                value={draft.asset_urn}
                onChange={(event) =>
                  onDraftChange({ ...draft, asset_urn: event.target.value })
                }
                spellCheck={false}
              />
            </label>
            <label>
              Source commit
              <input
                required
                value={draft.source_commit}
                onChange={(event) =>
                  onDraftChange({ ...draft, source_commit: event.target.value })
                }
              />
            </label>
          </details>

          <button
            className="button button-primary"
            disabled={busy}
            type="submit"
          >
            <Play aria-hidden="true" />
            {busy ? "Analyzing…" : "Analyze change"}
          </button>
        </>
      ) : null}
    </form>
  );
}
