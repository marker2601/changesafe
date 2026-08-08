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
]);

function publicMessage(error: unknown): string {
  return error instanceof Error
    ? error.message
    : "The request could not be completed.";
}

export function useRun(api: ChangeSafeApi) {
  const [config, setConfig] = useState<PublicConfig | null>(null);
  const [run, setRun] = useState<RunView | null>(null);
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const lastSequence = useRef(0);
  const reconnects = useRef(0);

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
      setBusy(true);
      setError(null);
      setEvents([]);
      lastSequence.current = 0;
      reconnects.current = 0;
      try {
        const created = await api.createRun(change);
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

  const reset = useCallback(() => {
    setRun(null);
    setEvents([]);
    setError(null);
    setActiveRunId(null);
    setBusy(false);
    lastSequence.current = 0;
    reconnects.current = 0;
  }, []);

  return { config, run, events, busy, error, analyze, approve, retry: approve, reset };
}
