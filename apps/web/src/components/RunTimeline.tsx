import { Check, Circle, CircleDot, TriangleAlert } from "lucide-react";

import type { RunEvent, RunState } from "../types";

const STEPS = [
  {
    label: "Reading the existing data contract",
    detail: "Schema, policy, ownership, and governance context.",
    eventState: "loading_context",
  },
  {
    label: "Finding everything that depends on cust_email",
    detail: "Models, semantic layers, reports, and teams.",
    eventState: "scoring_risk",
  },
  {
    label: "Classifying business and technical impact",
    detail: "Six evidence-led impact dimensions.",
    eventState: "scoring_risk",
  },
  {
    label: "Preparing a compatible migration",
    detail: "Seven deterministic migration artifacts.",
    eventState: "generating",
  },
  {
    label: "Proving the generated change is safe",
    detail: "All blocking checks must pass.",
    eventState: "validating",
  },
  {
    label: "Waiting for the accountable owner",
    detail: "Nothing publishes without authorization.",
    eventState: "awaiting_approval",
  },
  {
    label: "Publishing the approved change and evidence",
    detail: "Exact verified bytes and an auditable decision.",
    eventState: "publishing",
  },
] as const;

interface RunTimelineProps {
  events: RunEvent[];
  field: string;
  runState: RunState | null;
}

function activeIndex(state: RunState | null): number {
  if (state === "scoring_risk") return 2;
  if (state === "generating") return 3;
  if (state === "validating") return 4;
  if (state === "awaiting_approval") return 5;
  if (state === "preparing_preview" || state === "publishing") return 6;
  if (state === "completed") return STEPS.length;
  if (state === "publication_failed") return 6;
  if (state === "created" || state === "loading_context") return 0;
  return -1;
}

function eventMetadata(events: RunEvent[], eventState: string): string | null {
  const ordered = [...events].sort((left, right) => left.sequence - right.sequence);
  const event = ordered.find((candidate) => candidate.state === eventState);
  if (!event) return null;
  const eventLabel = `Event ${String(event.sequence).padStart(2, "0")}`;
  const eventTimestamp = Date.parse(event.created_at);
  const baseline = ordered
    .map((candidate) => Date.parse(candidate.created_at))
    .find((value) => Number.isFinite(value));
  if (!Number.isFinite(eventTimestamp) || baseline === undefined) return eventLabel;
  const milliseconds = Math.max(0, eventTimestamp - baseline);
  if (milliseconds < 1_000) return `${eventLabel} · +${milliseconds} ms`;
  const seconds = milliseconds / 1_000;
  return `${eventLabel} · +${seconds < 10 ? seconds.toFixed(1) : Math.round(seconds)} s`;
}

export function RunTimeline({ events, field, runState }: RunTimelineProps) {
  const progress = activeIndex(runState);
  const fallback = runState === "context_fallback_required";
  const failed = runState === "publication_failed";
  const steps = STEPS.map((step, index) =>
    index === 1
      ? { ...step, label: `Finding everything that depends on ${field}` }
      : step,
  );
  return (
    <aside className="timeline-panel" aria-labelledby="progress-heading">
      <header>
        <span>Persisted server events</span>
        <h2 id="progress-heading">Live change process</h2>
        <strong aria-live="polite">
          {runState ? runState.replaceAll("_", " ") : "Not started"}
        </strong>
      </header>
      <ol>
        {steps.map((step, index) => {
          const interrupted = (fallback && index === 0) || (failed && index === 6);
          const complete = !interrupted && index < progress;
          const active = !interrupted && index === progress;
          const status = interrupted
            ? "Interrupted"
            : complete
              ? "Complete"
              : active
                ? "In progress"
                : "Pending";
          return (
            <li
              className={
                interrupted
                  ? "is-interrupted"
                  : complete
                    ? "is-complete"
                    : active
                      ? "is-active"
                      : ""
              }
              data-testid="process-step"
              key={step.label}
            >
              <span className="timeline-icon">
                {interrupted ? (
                  <TriangleAlert aria-hidden="true" />
                ) : complete ? (
                  <Check aria-hidden="true" />
                ) : active ? (
                  <CircleDot aria-hidden="true" />
                ) : (
                  <Circle aria-hidden="true" />
                )}
              </span>
              <span className="timeline-content">
                <small>
                  {eventMetadata(events, step.eventState) ?? `Step 0${index + 1}`}
                </small>
                <strong>{step.label}</strong>
                <p>{step.detail}</p>
                <em>{status}</em>
              </span>
            </li>
          );
        })}
      </ol>
    </aside>
  );
}
