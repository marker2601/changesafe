import { Check, Circle, CircleDot, TriangleAlert } from "lucide-react";

import type {
  PublicationReceipt,
  RunEvent,
  RunState,
  WarehouseValidationResult,
} from "../types";

const STEPS = [
  {
    label: "Reading the existing data contract",
    detail: "Schema, policy, ownership, and governance context.",
    eventState: "loading_context",
  },
  {
    label: "Finding everything that depends on the requested field",
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
    detail: "The final action waits for authorization.",
    eventState: "awaiting_approval",
  },
  {
    label: "Finalizing the approved change package",
    detail: "The persisted run determines the authorized final action.",
    eventState: "completed",
  },
] as const;

interface RunTimelineProps {
  events: RunEvent[];
  field: string;
  publicationMode?: PublicationReceipt["mode"] | null;
  runState: RunState | null;
  warehouseValidation?: WarehouseValidationResult | null;
  warehouseValidationRequired?: boolean;
}

function activeIndex(state: RunState | null, warehouseStage: boolean): number {
  const approvalIndex = warehouseStage ? 6 : 5;
  const finalIndex = approvalIndex + 1;
  if (state === "scoring_risk") return 2;
  if (state === "generating") return 3;
  if (state === "validating") return 4;
  if (state === "validating_warehouse") return warehouseStage ? 5 : 4;
  if (state === "awaiting_approval") return approvalIndex;
  if (state === "preparing_preview" || state === "publishing") return finalIndex;
  if (state === "completed") return finalIndex + 1;
  if (state === "publication_failed") return finalIndex;
  if (state === "created" || state === "loading_context") return 0;
  return -1;
}

function phaseIndex(state: RunState, warehouseStage: boolean): number | null {
  const approvalIndex = warehouseStage ? 6 : 5;
  if (state === "created" || state === "loading_context") return 0;
  if (state === "scoring_risk") return 2;
  if (state === "generating") return 3;
  if (state === "validating") return 4;
  if (state === "validating_warehouse") return warehouseStage ? 5 : 4;
  if (state === "awaiting_approval") return approvalIndex;
  if (state === "preparing_preview" || state === "publishing") {
    return approvalIndex + 1;
  }
  return null;
}

function latestPersistedPhase(
  events: RunEvent[],
  fallback: number,
  warehouseStage: boolean,
): number {
  const ordered = [...events].sort((left, right) => right.sequence - left.sequence);
  for (const event of ordered) {
    const index = phaseIndex(event.state, warehouseStage);
    if (index !== null) return index;
  }
  return fallback;
}

function interruptedIndex(
  state: RunState | null,
  events: RunEvent[],
  warehouseStage: boolean,
): number | null {
  const finalIndex = warehouseStage ? 7 : 6;
  if (state === "context_fallback_required") {
    return latestPersistedPhase(events, 0, warehouseStage);
  }
  if (state === "failed") return latestPersistedPhase(events, 0, warehouseStage);
  if (state === "publication_failed") {
    return latestPersistedPhase(events, finalIndex, warehouseStage);
  }
  return null;
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

export function RunTimeline({
  events,
  field,
  publicationMode = null,
  runState,
  warehouseValidation = null,
  warehouseValidationRequired = false,
}: RunTimelineProps) {
  const durableMode =
    runState === "preparing_preview"
      ? "preview"
      : runState === "publishing" || runState === "publication_failed"
        ? "live"
        : publicationMode;
  const warehouseResultExists = Boolean(
    warehouseValidation && warehouseValidation.status !== "not_run",
  );
  const warehouseStage = Boolean(
    warehouseValidationRequired ||
      warehouseResultExists ||
      events.some((event) => event.state === "validating_warehouse"),
  );
  const interruption =
    runState === "failed" && warehouseValidation?.status === "blocked"
      ? 5
      : interruptedIndex(runState, events, warehouseStage);
  const progress = interruption ?? activeIndex(runState, warehouseStage);
  const finalStep =
    durableMode === "preview"
      ? {
          label: "Preparing the approved preview and evidence",
          detail: "A downloadable patch and non-mutating receipt; no systems change.",
          eventState: "preparing_preview",
        }
      : durableMode === "live"
        ? {
            label: "Publishing the approved change and evidence",
            detail: "Exact verified bytes and an auditable decision.",
            eventState: "publishing",
          }
        : STEPS.at(-1)!;
  const baseSteps = warehouseStage
    ? [
        ...STEPS.slice(0, 5),
        {
          label: "Validating aggregate warehouse evidence",
          detail: "Aggregate counts only; no source values leave the warehouse.",
          eventState: "validating_warehouse",
        },
        ...STEPS.slice(5),
      ]
    : [...STEPS];
  const approvalIndex = warehouseStage ? 6 : 5;
  const steps = baseSteps.map((step, index) => {
    if (index === 1) {
      return { ...step, label: `Finding everything that depends on ${field}` };
    }
    if (index === approvalIndex) {
      const detail =
        durableMode === "live"
          ? "Nothing publishes without authorization."
          : durableMode === "preview"
            ? "The verified preview waits for authorization."
            : step.detail;
      return { ...step, detail };
    }
    return index === baseSteps.length - 1 ? finalStep : step;
  });
  return (
    <aside className="timeline-panel" aria-labelledby="progress-heading">
      <header>
        <span>Persisted server events</span>
        <h2 id="progress-heading">Change process</h2>
        <strong aria-live="polite">
          {runState ? runState.replaceAll("_", " ") : "Not started"}
        </strong>
      </header>
      <ol>
        {steps.map((step, index) => {
          const interrupted = index === interruption;
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
                  {eventMetadata(events, step.eventState) ??
                    `Step ${String(index + 1).padStart(2, "0")}`}
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
