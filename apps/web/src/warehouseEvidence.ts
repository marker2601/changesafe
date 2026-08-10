import type { ContextBundle, WarehouseValidationResult } from "./types";

export function blockedBeforeProductionQuery(
  validation: WarehouseValidationResult,
): boolean {
  return (
    validation.status === "blocked" &&
    validation.aggregate_query_started === false
  );
}

export function warehouseValidationClaim(
  validation: WarehouseValidationResult,
  contextMode: ContextBundle["provenance"]["mode"],
): string {
  if (validation.aggregate_query_started === false) {
    return "Production rows not queried";
  }
  if (validation.aggregate_query_started === null) {
    return `Warehouse query status unavailable · ${validation.environment_label}`;
  }
  if (
    contextMode === "live" &&
    validation.status === "passed" &&
    validation.mode === "aggregate"
  ) {
    return `Warehouse values checked · ${validation.environment_label}`;
  }
  return `Warehouse validation inconclusive · ${validation.environment_label}`;
}
