import { Play } from "lucide-react";
import { useState, type FormEvent } from "react";

import type { ChangeOperation, ChangeRequest } from "../types";

const TARGET =
  "urn:li:dataset:(urn:li:dataPlatform:dbt,analytics.dim_customers,PROD)";

interface ChangeFormProps {
  busy: boolean;
  onSubmit: (change: ChangeRequest) => void | Promise<void>;
}

export function ChangeForm({ busy, onSubmit }: ChangeFormProps) {
  const [assetUrn, setAssetUrn] = useState(TARGET);
  const [operation, setOperation] = useState<ChangeOperation>("rename");
  const [field, setField] = useState("customer_email");
  const [newField, setNewField] = useState("primary_email");
  const [oldType, setOldType] = useState("STRING");
  const [newType, setNewType] = useState("VARCHAR");
  const [sourceCommit, setSourceCommit] = useState("demo-unsafe-change");

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void onSubmit({
      asset_urn: assetUrn,
      operation,
      field,
      new_field: operation === "rename" ? newField : null,
      old_type: operation === "type_change" ? oldType : "STRING",
      new_type: operation === "type_change" ? newType : "STRING",
      source_commit: sourceCommit,
      requested_by: "demo-user",
    });
  };

  return (
    <form className="change-form" onSubmit={submit}>
      <div className="section-heading">
        <h2>Propose a schema change</h2>
        <p>Analyze the metadata blast radius before merge.</p>
      </div>

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
        Operation
        <select
          value={operation}
          onChange={(event) =>
            setOperation(event.target.value as ChangeOperation)
          }
        >
          <option value="rename">Rename</option>
          <option value="remove">Remove</option>
          <option value="type_change">Type change</option>
        </select>
      </label>
      <label>
        Current field
        <input
          required
          value={field}
          onChange={(event) => setField(event.target.value)}
        />
      </label>
      {operation === "rename" ? (
        <label>
          New field
          <input
            required
            value={newField}
            onChange={(event) => setNewField(event.target.value)}
          />
        </label>
      ) : null}
      {operation === "type_change" ? (
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
      <label>
        Source commit
        <input
          required
          value={sourceCommit}
          onChange={(event) => setSourceCommit(event.target.value)}
        />
      </label>
      <button className="button button-primary" disabled={busy} type="submit">
        <Play aria-hidden="true" />
        {busy ? "Analyzing…" : "Analyze change"}
      </button>
    </form>
  );
}
