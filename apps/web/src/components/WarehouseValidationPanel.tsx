import { Check, Database, TriangleAlert, X } from "lucide-react";

import type {
  ChangeOperation,
  WarehouseValidationResult,
} from "../types";
import {
  blockedBeforeProductionQuery,
  warehouseValidationClaim,
} from "../warehouseEvidence";

interface WarehouseValidationPanelProps {
  validation: WarehouseValidationResult;
}

const OPERATION_LABELS: Record<ChangeOperation, string> = {
  rename: "Rename",
  remove: "Remove",
  type_change: "Type change",
};

function countFacts(validation: WarehouseValidationResult) {
  return [
    ["Rows evaluated", validation.rows_evaluated],
    ["Populated rows", validation.populated_row_count],
    ["Unsafe rows", validation.unsafe_row_count],
  ] as const;
}

export function WarehouseValidationPanel({
  validation,
}: WarehouseValidationPanelProps) {
  const facts = countFacts(validation).filter(([, value]) => value !== null);
  const passedAggregate =
    validation.status === "passed" && validation.mode === "aggregate";
  const blockedBeforeQuery =
    blockedBeforeProductionQuery(validation);
  const statusClaim = warehouseValidationClaim(validation);
  const statusDetail = passedAggregate
    ? "Aggregate warehouse evidence passed every recorded warehouse check."
    : validation.status === "not_run"
      ? "No aggregate warehouse validation was run for this analysis."
      : blockedBeforeQuery
        ? "Warehouse validation was blocked before aggregate production-row evidence was returned."
        : "Aggregate validation was inconclusive and approval remains blocked.";
  const StatusIcon = passedAggregate
    ? Check
    : validation.status === "blocked"
      ? TriangleAlert
      : Database;

  return (
    <section
      aria-labelledby="warehouse-validation-heading"
      className={`warehouse-validation-panel warehouse-status-${validation.status}`}
      id="warehouse-validation"
    >
      <h2 id="warehouse-validation-heading">Warehouse validation</h2>
      <div className="warehouse-status" role="status">
        <span aria-hidden="true">
          <StatusIcon />
        </span>
        <div>
          <strong>{statusClaim}</strong>
          <p>{statusDetail}</p>
        </div>
      </div>

      <dl className="warehouse-scope">
        <div>
          <dt>Environment</dt>
          <dd>{validation.environment_label}</dd>
        </div>
        <div>
          <dt>Operation</dt>
          <dd>{OPERATION_LABELS[validation.operation]}</dd>
        </div>
        <div>
          <dt>Field</dt>
          <dd>{validation.field}</dd>
        </div>
      </dl>

      {facts.length > 0 || validation.elapsed_ms !== null ? (
        <dl className="warehouse-counts">
          {facts.map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
          {validation.elapsed_ms !== null ? (
            <div>
              <dt>Elapsed</dt>
              <dd>{validation.elapsed_ms} ms</dd>
            </div>
          ) : null}
        </dl>
      ) : null}

      {validation.checks.length > 0 ? (
        <div className="warehouse-checks">
          <h3>Warehouse checks</h3>
          <ol>
            {validation.checks.map((check) => (
              <li className={check.passed ? "is-passed" : "is-blocked"} key={check.code}>
                {check.passed ? (
                  <Check aria-hidden="true" />
                ) : (
                  <X aria-hidden="true" />
                )}
                <span>
                  <strong>{check.label}</strong>
                  <small>{check.detail}</small>
                  {check.observed_count !== null ? (
                    <em>Observed count: {check.observed_count}</em>
                  ) : null}
                  {!check.passed && check.retryable ? <em>Retryable</em> : null}
                </span>
              </li>
            ))}
          </ol>
        </div>
      ) : null}

      {validation.query_ids.length > 0 ? (
        <details className="warehouse-audit-identifiers">
          <summary>Technical audit identifiers</summary>
          <ul>
            {validation.query_ids.map((queryId) => (
              <li key={queryId}>
                <code>{queryId}</code>
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </section>
  );
}
