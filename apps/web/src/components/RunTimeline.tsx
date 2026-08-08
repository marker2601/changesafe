import { Check, CircleDot } from "lucide-react";

import type { RunEvent, RunState } from "../types";

const PHASES: Array<{ state: RunState; label: string }> = [
  { state: "loading_context", label: "Context loaded" },
  { state: "scoring_risk", label: "Risk scored" },
  { state: "generating", label: "Artifacts generated" },
  { state: "validating", label: "Validation passed" },
  { state: "awaiting_approval", label: "Awaiting approval" },
];

interface RunTimelineProps {
  events: RunEvent[];
  runState: RunState | null;
}

export function RunTimeline({ events, runState }: RunTimelineProps) {
  const phaseForState = PHASES.findIndex((phase) => phase.state === runState);
  const furthestEvent = events.reduce(
    (furthest, event) =>
      Math.max(
        furthest,
        PHASES.findIndex((phase) => phase.state === event.state),
      ),
    -1,
  );
  const progress =
    runState === "completed" ||
    runState === "preparing_preview" ||
    runState === "publishing" ||
    runState === "publication_failed"
      ? PHASES.length
      : runState === "context_fallback_required"
        ? 0
        : phaseForState >= 0
          ? phaseForState
          : furthestEvent;
  const approved = runState === "completed";
  return (
    <aside className="timeline-panel" aria-labelledby="progress-heading">
      <h2 id="progress-heading">Run progress</h2>
      <ol>
        {PHASES.map((phase, index) => {
          const reached = index < progress;
          const active = runState === phase.state;
          const label =
            approved && phase.state === "awaiting_approval"
              ? "Approved"
              : phase.label;
          return (
            <li
              className={active ? "is-active" : reached ? "is-complete" : ""}
              key={phase.state}
            >
              <span className="timeline-icon">
                {reached && !active ? (
                  <Check aria-hidden="true" />
                ) : (
                  <CircleDot aria-hidden="true" />
                )}
              </span>
              <span>
                <strong>{label}</strong>
                <small>{active ? "In progress" : reached ? "Complete" : "Pending"}</small>
              </span>
            </li>
          );
        })}
      </ol>
    </aside>
  );
}
