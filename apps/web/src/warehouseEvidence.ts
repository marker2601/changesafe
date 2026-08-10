import type { WarehouseValidationResult } from "./types";

const BEFORE_PRODUCTION_QUERY_CODES = new Set([
  "warehouse_authentication",
  "warehouse_contract",
  "warehouse_identity",
  "warehouse_query",
  "warehouse_relation",
  "warehouse_schema",
]);

export function blockedBeforeProductionQuery(
  validation: WarehouseValidationResult,
): boolean {
  const counts = [
    validation.rows_evaluated,
    validation.populated_row_count,
    validation.unsafe_row_count,
  ];
  return (
    validation.status === "blocked" &&
    counts.every((value) => value === null) &&
    validation.checks.length > 0 &&
    validation.checks.every((check) =>
      BEFORE_PRODUCTION_QUERY_CODES.has(check.code),
    )
  );
}

export function warehouseValidationClaim(
  validation: WarehouseValidationResult,
): string {
  if (validation.status === "passed" && validation.mode === "aggregate") {
    return `Warehouse values checked · ${validation.environment_label}`;
  }
  if (
    validation.status === "not_run" ||
    blockedBeforeProductionQuery(validation)
  ) {
    return "Production rows not queried";
  }
  return `Warehouse validation inconclusive · ${validation.environment_label}`;
}
