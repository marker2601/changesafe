import { ArrowRight, Database, Play, ShieldCheck, Snowflake } from "lucide-react";
import { useState, type FormEvent } from "react";

import type { ChangeOperation, ChangeRequest } from "../types";

const TARGET =
  "urn:li:dataset:(urn:li:dataPlatform:dbt,b2fd91.ORDER_ENTRY_DB.analytics.order_details,PROD)";

interface ChangeFormProps {
  busy: boolean;
  onSubmit: (change: ChangeRequest) => void | Promise<void>;
  submitted?: boolean;
}

export function ChangeForm({ busy, onSubmit, submitted = false }: ChangeFormProps) {
  const [assetUrn, setAssetUrn] = useState(TARGET);
  const [operation, setOperation] = useState<ChangeOperation>("rename");
  const [field, setField] = useState("cust_email");
  const [newField, setNewField] = useState("primary_email");
  const [oldType, setOldType] = useState("TEXT");
  const [newType, setNewType] = useState("VARCHAR(320)");
  const [sourceCommit, setSourceCommit] = useState(
    "showcase-ecommerce-safe-rename",
  );

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void onSubmit({
      asset_urn: assetUrn,
      operation,
      field,
      new_field: operation === "rename" ? newField : null,
      old_type: operation === "type_change" ? oldType : null,
      new_type: operation === "type_change" ? newType : null,
      source_commit: sourceCommit,
      requested_by: "judge-demo",
    });
  };

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
            : "Propose the rename. ChangeSafe will discover who and what it affects."}
        </p>
      </header>

      {!submitted ? (
        <label>
          Operation
          <select
            value={operation}
            onChange={(event) =>
              setOperation(event.target.value as ChangeOperation)
            }
          >
            <option value="rename">Rename field</option>
            <option value="remove">Remove field</option>
            <option value="type_change">Change type</option>
          </select>
        </label>
      ) : null}

      <p className="change-route" aria-label="Proposed field transition">
        <strong>{field}</strong>
        <ArrowRight aria-hidden="true" />
        <strong>{operation === "rename" ? newField : operation.replace("_", " ")}</strong>
      </p>

      {!submitted ? (
        <div className="rename-pair">
          <label>
            Current field
            <input
              required
              value={field}
              onChange={(event) => setField(event.target.value)}
            />
          </label>
          <ArrowRight aria-hidden="true" />
          {operation === "rename" ? (
            <label>
              New field
              <input
                required
                value={newField}
                onChange={(event) => setNewField(event.target.value)}
              />
            </label>
          ) : (
            <span className="operation-destination">
              {operation === "remove"
                ? "Retain temporarily"
                : "Compatible alias"}
            </span>
          )}
        </div>
      ) : null}

      {!submitted && operation === "type_change" ? (
        <div className="field-pair">
          <label>
            Current type
            <input
              required
              value={oldType}
              onChange={(event) => setOldType(event.target.value)}
            />
          </label>
          <label>
            New type
            <input
              required
              value={newType}
              onChange={(event) => setNewType(event.target.value)}
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
                value={assetUrn}
                onChange={(event) => setAssetUrn(event.target.value)}
                spellCheck={false}
              />
            </label>
            <label>
              Source commit
              <input
                required
                value={sourceCommit}
                onChange={(event) => setSourceCommit(event.target.value)}
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
