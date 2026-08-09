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

interface CatalogResult {
  key: string;
  catalog: SchemaCatalog | null;
  error: string | null;
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
  const [result, setResult] = useState<CatalogResult>({
    key: "",
    catalog: null,
    error: null,
  });
  const requestId = useRef(0);
  const source =
    sourceState.assetUrn === assetUrn ? sourceState.source : "active";
  const key = cacheKey(source, assetUrn);
  const validUrn = DATASET_URN.test(assetUrn);
  const cached = validUrn ? catalogCache.get(key) ?? null : null;
  const currentResult = result.key === key ? result : null;
  const catalog = currentResult?.catalog ?? cached;
  const error = currentResult?.error ?? null;
  const loading = validUrn && catalog === null && error === null;

  useEffect(() => {
    if (sourceState.assetUrn === assetUrn) return;
    let current = true;
    queueMicrotask(() => {
      if (!current) return;
      setSourceState({ assetUrn, source: "active" });
    });
    return () => {
      current = false;
    };
  }, [assetUrn, sourceState.assetUrn]);

  useEffect(() => {
    const request = ++requestId.current;
    let current = true;
    if (!validUrn || cached) return () => {
      current = false;
    };

    void api
      .getSchemaCatalog(assetUrn, source)
      .then((value) => {
        if (!current || request !== requestId.current) return;
        catalogCache.set(key, value);
        setResult({ key, catalog: value, error: null });
      })
      .catch((reason: unknown) => {
        if (!current || request !== requestId.current) return;
        setResult({ key, catalog: null, error: publicError(reason) });
      });

    return () => {
      current = false;
    };
  }, [api, assetUrn, cached, key, source, validUrn, attempt]);

  const retry = useCallback(() => {
    setAttempt((current) => current + 1);
  }, []);
  const loadRecorded = useCallback(() => {
    setSourceState({ assetUrn, source: "recorded" });
    setAttempt((current) => current + 1);
  }, [assetUrn]);

  return { catalog, loading, error, source, retry, loadRecorded };
}
