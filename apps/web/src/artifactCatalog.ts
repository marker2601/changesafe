export interface ArtifactExplanation {
  label: string;
  purpose: string;
  prevents: string;
}

const EXPLANATIONS = {
  modelSql: {
    label: "dbt model SQL",
    purpose:
      "Preserves the current field and adds the compatible alias or cast when required.",
    prevents: "Breaking existing consumers during phase one.",
  },
  modelYaml: {
    label: "dbt model YAML",
    purpose:
      "Enforces the output contract using DataHub-backed names, types, and nullability.",
    prevents: "SQL/YAML drift and invented constraints.",
  },
  test: {
    label: "Compatibility test",
    purpose:
      "Checks old and new outputs, or guards the old field when dbt runs a deferred-removal test.",
    prevents: "Silent divergence or premature removal.",
  },
  migration: {
    label: "Migration notes",
    purpose:
      "Records owners, evidence, the migration window, affected consumers, and exit criteria.",
    prevents: "An uncoordinated phase-two change.",
  },
  rollback: {
    label: "Rollback guide",
    purpose: "Identifies the exact generated files and their safe recovery order.",
    prevents: "An incomplete or unsafe reversal.",
  },
  prBody: {
    label: "Pull-request body",
    purpose: "Summarizes deterministic risk, impact, and verification gates.",
    prevents: "Publishing without reviewer context.",
  },
  manifest: {
    label: "Verification manifest",
    purpose:
      "Binds the request, evidence checksum, risk, paths, and exact UTF-8 file hashes.",
    prevents: "Artifact substitution or drift after verification.",
  },
  fallback: {
    label: "Generated file",
    purpose: "Carries a generated part of the verified change package for review.",
    prevents: "Publishing an unexplained file without review.",
  },
} as const satisfies Record<string, ArtifactExplanation>;

export function artifactExplanation(path: string): ArtifactExplanation {
  const normalized = path.replaceAll("\\", "/").toLowerCase();
  if (normalized.startsWith("tests/") && normalized.endsWith(".sql")) {
    return EXPLANATIONS.test;
  }
  if (normalized.startsWith("models/") && normalized.endsWith(".sql")) {
    return EXPLANATIONS.modelSql;
  }
  if (
    normalized.startsWith("models/") &&
    (normalized.endsWith(".yml") || normalized.endsWith(".yaml"))
  ) {
    return EXPLANATIONS.modelYaml;
  }
  if (normalized.startsWith("migrations/")) return EXPLANATIONS.migration;
  if (normalized === "rollback.md") return EXPLANATIONS.rollback;
  if (normalized === "pr_body.md") return EXPLANATIONS.prBody;
  if (normalized === "changesafe-manifest.json") return EXPLANATIONS.manifest;
  return EXPLANATIONS.fallback;
}
