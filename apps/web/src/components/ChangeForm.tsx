import { ArrowRight, Database, Play, ShieldCheck, Snowflake } from "lucide-react";
import type { FormEvent } from "react";

import {
  changeSummary,
  draftToRequest,
  sourceCommitForOperation,
  type ChangeDraft,
} from "../changeDraft";
import type { ChangeOperation, ChangeRequest } from "../types";

interface ChangeFormProps {
  busy: boolean;
  draft: ChangeDraft;
  onDraftChange: (draft: ChangeDraft) => void;
  onSubmit: (change: ChangeRequest) => void | Promise<void>;
  submittedRequest?: ChangeRequest | null;
}

export function ChangeForm({
  busy,
  draft,
  onDraftChange,
  onSubmit,
  submittedRequest = null,
}: ChangeFormProps) {
  const submitted = submittedRequest !== null;
  const displayed = submittedRequest ?? draft;
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
        <span>Official ecommerce scenario</span>
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
            <Database aria-hidden="true" /> Data product
          </dt>
          <dd>Order Entry Analytics</dd>
        </div>
        <div>
          <dt>
            <ShieldCheck aria-hidden="true" /> Field policy
          </dt>
          <dd>PII · Governed</dd>
        </div>
        <div>
          <dt>
            <Snowflake aria-hidden="true" /> Source system
          </dt>
          <dd>Snowflake · dbt</dd>
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
