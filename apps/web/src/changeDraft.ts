import type { ChangeOperation, ChangeRequest } from "./types";

export const OFFICIAL_TARGET =
  "urn:li:dataset:(urn:li:dataPlatform:dbt,b2fd91.ORDER_ENTRY_DB.analytics.order_details,PROD)";

export interface ChangeDraft {
  asset_urn: string;
  operation: ChangeOperation;
  field: string;
  new_field: string;
  old_type: string;
  new_type: string;
  source_commit: string;
}

type ChangeSummaryInput = Pick<
  ChangeRequest,
  "operation" | "field" | "new_field" | "new_type"
>;

const OPERATION_COMMITS = {
  rename: "showcase-ecommerce-safe-rename",
  remove: "showcase-ecommerce-safe-remove",
  type_change: "showcase-ecommerce-safe-type-change",
} satisfies Record<ChangeOperation, string>;

export function sourceCommitForOperation(operation: ChangeOperation): string {
  return OPERATION_COMMITS[operation];
}

export function isOfficialDataset(
  change: Pick<ChangeDraft, "asset_urn">,
): boolean {
  return change.asset_urn === OFFICIAL_TARGET;
}

type ScenarioRequest = Pick<
  ChangeRequest,
  | "asset_urn"
  | "operation"
  | "field"
  | "new_field"
  | "old_type"
  | "new_type"
  | "source_commit"
>;

export function isOfficialScenario(
  change: ChangeDraft | ScenarioRequest,
): boolean {
  if (
    change.asset_urn !== OFFICIAL_TARGET ||
    change.field !== "cust_email" ||
    change.source_commit !== sourceCommitForOperation(change.operation)
  ) {
    return false;
  }
  if (change.operation === "rename") return change.new_field === "primary_email";
  if (change.operation === "type_change") {
    return change.old_type === "TEXT" && change.new_type === "VARCHAR(320)";
  }
  return true;
}

export const DEFAULT_CHANGE_DRAFT: ChangeDraft = {
  asset_urn: OFFICIAL_TARGET,
  operation: "rename",
  field: "cust_email",
  new_field: "primary_email",
  old_type: "TEXT",
  new_type: "VARCHAR(320)",
  source_commit: sourceCommitForOperation("rename"),
};

export function draftToRequest(draft: ChangeDraft): ChangeRequest {
  return {
    asset_urn: draft.asset_urn,
    operation: draft.operation,
    field: draft.field,
    new_field: draft.operation === "rename" ? draft.new_field : null,
    old_type: draft.operation === "type_change" ? draft.old_type : null,
    new_type: draft.operation === "type_change" ? draft.new_type : null,
    source_commit: draft.source_commit,
    requested_by: "changesafe-web",
  };
}

export function changeSummary(change: ChangeSummaryInput): string {
  if (change.operation === "rename") {
    if (!change.new_field?.trim()) {
      return `Choose the new field name for ${change.field} before analysis.`;
    }
    return `Keep ${change.field} available while consumers move to ${change.new_field}.`;
  }
  if (change.operation === "remove") {
    return `Delay removal of ${change.field} until every recorded consumer has migrated.`;
  }
  if (!change.new_type?.trim()) {
    return `Choose the new type for ${change.field} before analysis.`;
  }
  return (
    `Keep ${change.field} and add a safely cast ${change.new_type} ` +
    "compatibility field during phase one."
  );
}
