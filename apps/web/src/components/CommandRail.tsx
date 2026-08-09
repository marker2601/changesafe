import {
  Check,
  FileCheck2,
  LockKeyhole,
  Radar,
  ScanSearch,
  ShieldCheck,
} from "lucide-react";

import type { RunState } from "../types";

interface CommandRailProps {
  artifactCount: number;
  passedChecks: number;
  totalChecks: number;
  runState: RunState | null;
}

const STAGES = [
  { label: "Observe", detail: "Read DataHub context", icon: Radar },
  { label: "Understand", detail: "Classify impact", icon: ScanSearch },
  { label: "Prepare", detail: "Generate verified files", icon: FileCheck2 },
  { label: "Prove", detail: "Run blocking checks", icon: ShieldCheck },
  { label: "Authorize", detail: "Owner decision", icon: LockKeyhole },
] as const;

function stageProgress(state: RunState | null): number {
  if (state === "scoring_risk") return 1;
  if (state === "generating") return 2;
  if (state === "validating") return 3;
  if (state === "awaiting_approval") return 4;
  if (
    state === "preparing_preview" ||
    state === "publishing" ||
    state === "completed" ||
    state === "publication_failed"
  )
    return 5;
  return 0;
}

export function CommandRail({
  artifactCount,
  passedChecks,
  totalChecks,
  runState,
}: CommandRailProps) {
  const progress = stageProgress(runState);
  return (
    <section className="command-rail" aria-label="Change safety gates">
      <ol>
        {STAGES.map((stage, index) => {
          const Icon = stage.icon;
          const complete = index < progress;
          const active = index === progress && progress < STAGES.length;
          const detail =
            stage.label === "Prepare" && artifactCount
              ? `${artifactCount} verified files`
              : stage.label === "Prove" && totalChecks
                ? `${passedChecks} / ${totalChecks} blocking checks`
                : stage.detail;
          return (
            <li
              className={complete ? "is-complete" : active ? "is-active" : ""}
              key={stage.label}
            >
              <span className="gate-number">{index + 1}</span>
              <Icon aria-hidden="true" />
              <span>
                <strong>{stage.label}</strong>
                <small>{detail}</small>
              </span>
              {complete ? <Check aria-hidden="true" /> : null}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
