import { useCallback, useEffect, useRef, useState } from "react";

import type {
  ChangeSafeApi,
  SchemaCatalog,
  SchemaEvidenceSource,
} from "../types";

const catalogCache = new Map<string, SchemaCatalog>();
const DATASET_URN = /^urn:li:dataset:/;

export interface SchemaCatalogState {
  catalog: SchemaCatalog | null;
  loading: boolean;
  error: string | null;
  source: SchemaEvidenceSource;
  retry(): void;
  loadRecorded(): void;
}

function cacheKey(source: SchemaEvidenceSource, assetUrn: string): string {
  return `${source}:${assetUrn}`;
}

function publicError(reason: unknown): string {
  return reason instanceof Error
    ? reason.message
    : "Schema fields could not be read safely.";
}

export function useSchemaCatalog(
  api: ChangeSafeApi,
  assetUrn: string,
): SchemaCatalogState {
  const [sourceState, setSourceState] = useState<{
    assetUrn: string;
    source: SchemaEvidenceSource;
  }>({ assetUrn, source: "active" });
  const [attempt, setAttempt] = useState(0);
  const [catalog, setCatalog] = useState<SchemaCatalog | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestId = useRef(0);

  const source =
    sourceState.assetUrn === assetUrn ? sourceState.source : "active";

  useEffect(() => {
    const request = ++requestId.current;
    let current = true;
    if (!DATASET_URN.test(assetUrn)) {
      queueMicrotask(() => {
        if (!current) return;
        setCatalog(null);
        setLoading(false);
        setError(null);
      });
      return () => {
        current = false;
      };
    }

    const cached = catalogCache.get(cacheKey(source, assetUrn));
    if (cached) {
      queueMicrotask(() => {
        if (!current) return;
        setCatalog(cached);
        setLoading(false);
        setError(null);
      });
      return () => {
        current = false;
      };
    }

    queueMicrotask(() => {
      if (!current || request !== requestId.current) return;
      setCatalog(null);
      setLoading(true);
      setError(null);
      void api
        .getSchemaCatalog(assetUrn, source)
        .then((value) => {
          if (!current || request !== requestId.current) return;
          catalogCache.set(cacheKey(source, assetUrn), value);
          setCatalog(value);
          setLoading(false);
        })
        .catch((reason: unknown) => {
          if (!current || request !== requestId.current) return;
          setCatalog(null);
          setError(publicError(reason));
          setLoading(false);
        });
    });

    return () => {
      current = false;
    };
  }, [api, assetUrn, source, attempt]);

  const retry = useCallback(() => {
    setAttempt((current) => current + 1);
  }, []);
  const loadRecorded = useCallback(() => {
    setSourceState({ assetUrn, source: "recorded" });
    setAttempt((current) => current + 1);
  }, [assetUrn]);

  return { catalog, loading, error, source, retry, loadRecorded };
}
