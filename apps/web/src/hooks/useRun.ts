import { useCallback, useEffect, useRef, useState } from "react";

import type {
  ChangeRequest,
  ChangeSafeApi,
  PublicConfig,
  RunEvent,
  RunState,
  RunView,
} from "../types";

const STREAM_END_STATES = new Set<RunState>([
  "awaiting_approval",
  "completed",
  "failed",
  "publication_failed",
  "context_fallback_required",
]);

const RECOVERED_ACTION_STATES = new Set<RunState>([
  "preparing_preview",
  "publishing",
]);

export const RUN_SESSION_KEY = "changesafe.active-run.v1";

interface PersistedRunSession {
  runId: string;
  lastSequence: number;
}

function readRunSession(): PersistedRunSession | null {
  try {
    const raw = window.sessionStorage.getItem(RUN_SESSION_KEY);
    if (!raw) return null;
    const value = JSON.parse(raw) as Partial<PersistedRunSession>;
    if (
      typeof value.runId !== "string" ||
      !value.runId ||
      !Number.isInteger(value.lastSequence) ||
      (value.lastSequence ?? -1) < 0
    ) {
      window.sessionStorage.removeItem(RUN_SESSION_KEY);
      return null;
    }
    return value as PersistedRunSession;
  } catch {
    return null;
  }
}

function persistRunSession(runId: string, lastSequence: number): void {
  try {
    window.sessionStorage.setItem(
      RUN_SESSION_KEY,
      JSON.stringify({ runId, lastSequence }),
    );
  } catch {
    // Session persistence is a recovery aid; the live run remains usable without it.
  }
}

function clearRunSession(): void {
  try {
    window.sessionStorage.removeItem(RUN_SESSION_KEY);
  } catch {
    // Ignore browsers that deny storage access.
  }
}

function publicMessage(error: unknown): string {
  return error instanceof Error
    ? error.message
    : "The request could not be completed.";
}

export function useRun(api: ChangeSafeApi) {
  const [recoveredSession] = useState<PersistedRunSession | null>(() =>
    readRunSession(),
  );
  const [config, setConfig] = useState<PublicConfig | null>(null);
  const [run, setRun] = useState<RunView | null>(null);
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [busy, setBusy] = useState(recoveredSession !== null);
  const [error, setError] = useState<string | null>(null);
  const lastSequence = useRef(0);
  const reconnects = useRef(0);
  const recoveryActive = useRef(recoveredSession !== null);

  useEffect(() => {
    if (!recoveredSession || !recoveryActive.current) return undefined;
    let current = true;
    api
      .getRun(recoveredSession.runId)
      .then((value) => {
        if (!current || !recoveryActive.current) return;
        recoveryActive.current = false;
        lastSequence.current = 0;
        reconnects.current = 0;
        setEvents([]);
        setRun(value);
        setActiveRunId(value.run_id);
        setBusy(!RECOVERED_ACTION_STATES.has(value.state));
      })
      .catch((reason: unknown) => {
        if (!current || !recoveryActive.current) return;
        recoveryActive.current = false;
        clearRunSession();
        setError(`Saved run could not be restored. ${publicMessage(reason)}`);
        setBusy(false);
      });
    return () => {
      current = false;
    };
  }, [api, recoveredSession]);

  useEffect(() => {
    let current = true;
    api
      .getPublicConfig()
      .then((value) => {
        if (current) setConfig(value);
      })
      .catch((reason: unknown) => {
        if (current) setError(publicMessage(reason));
      });
    return () => {
      current = false;
    };
  }, [api]);

  useEffect(() => {
    if (!activeRunId) return undefined;
    let disposed = false;
    let unsubscribe: (() => void) | undefined;

    const finish = async () => {
      try {
        const finalRun = await api.getRun(activeRunId);
        if (!disposed) {
          setRun(finalRun);
          setBusy(false);
          setActiveRunId(null);
        }
      } catch (reason) {
        if (!disposed) {
          setError(publicMessage(reason));
          setBusy(false);
        }
      }
    };

    const connect = () => {
      unsubscribe = api.subscribe(
        activeRunId,
        lastSequence.current,
        (event) => {
          if (disposed || event.sequence <= lastSequence.current) return;
          lastSequence.current = event.sequence;
          persistRunSession(activeRunId, event.sequence);
          setEvents((current) => [...current, event]);
          setRun((current) =>
            current ? { ...current, state: event.state } : current,
          );
          if (STREAM_END_STATES.has(event.state)) {
            unsubscribe?.();
            void finish();
          }
        },
        () => {
          unsubscribe?.();
          if (disposed) return;
          if (reconnects.current < 1) {
            reconnects.current += 1;
            connect();
          } else {
            setError("Live progress disconnected. Refresh to resume this run.");
            setBusy(false);
          }
        },
      );
    };

    connect();
    return () => {
      disposed = true;
      unsubscribe?.();
    };
  }, [activeRunId, api]);

  const analyze = useCallback(
    async (change: ChangeRequest) => {
      recoveryActive.current = false;
      setBusy(true);
      setError(null);
      setEvents([]);
      lastSequence.current = 0;
      reconnects.current = 0;
      try {
        const created = await api.createRun(change);
        persistRunSession(created.run_id, 0);
        setRun(created);
        setActiveRunId(created.run_id);
      } catch (reason) {
        setError(publicMessage(reason));
        setBusy(false);
      }
    },
    [api],
  );

  const approve = useCallback(
    async (adminToken?: string) => {
      if (!run) return;
      setBusy(true);
      setError(null);
      persistRunSession(run.run_id, lastSequence.current);
      try {
        await api.approve(run.run_id, adminToken);
        setRun(await api.getRun(run.run_id));
      } catch (reason) {
        try {
          setRun(await api.getRun(run.run_id));
        } catch {
          // Preserve the existing run when the refresh also fails.
        }
        setError(publicMessage(reason));
      } finally {
        setBusy(false);
      }
    },
    [api, run],
  );

  const continueWithSnapshot = useCallback(async () => {
    if (!run || run.state !== "context_fallback_required") return;
    setBusy(true);
    setError(null);
    reconnects.current = 0;
    try {
      const continued = await api.continueWithSnapshot(run.run_id);
      persistRunSession(run.run_id, lastSequence.current);
      setRun(continued);
      setActiveRunId(run.run_id);
    } catch (reason) {
      setError(publicMessage(reason));
      setBusy(false);
    }
  }, [api, run]);

  const reset = useCallback(() => {
    recoveryActive.current = false;
    setRun(null);
    setEvents([]);
    setError(null);
    setActiveRunId(null);
    setBusy(false);
    lastSequence.current = 0;
    reconnects.current = 0;
    clearRunSession();
  }, []);

  return {
    config,
    run,
    events,
    busy,
    error,
    analyze,
    approve,
    continueWithSnapshot,
    retry: approve,
    reset,
  };
}
