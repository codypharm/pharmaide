import { useCallback, useEffect, useRef, useState } from "react";

import {
  getKnowledgeDocument,
  type KnowledgeDocumentStatus,
  type KnowledgeDocumentView,
  type KnowledgeScope,
} from "../api/knowledge";

const POLL_DELAY_MS = 3_000;

export type DocumentIngestionHookStatus = KnowledgeDocumentStatus | "idle" | "loading";

export type UseDocumentIngestionStatusResult = {
  status: DocumentIngestionHookStatus;
  data: KnowledgeDocumentView | null;
  error: unknown;
  refresh: () => Promise<void>;
};

function shouldPoll(status: DocumentIngestionHookStatus): boolean {
  return status === "ingesting";
}

export function useDocumentIngestionStatus(
  documentId: string | null,
  scope: KnowledgeScope,
): UseDocumentIngestionStatusResult {
  const scopeId = scope.scopeId;
  const [data, setData] = useState<KnowledgeDocumentView | null>(null);
  const [status, setStatus] = useState<DocumentIngestionHookStatus>(
    documentId ? "loading" : "idle",
  );
  const [error, setError] = useState<unknown>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const requestVersionRef = useRef(0);

  const clearPollTimer = useCallback(() => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const poll = useCallback(async () => {
    clearPollTimer();
    if (!documentId) {
      setStatus("idle");
      setData(null);
      setError(null);
      return;
    }

    const requestVersion = ++requestVersionRef.current;
    try {
      const next = await getKnowledgeDocument(documentId, { scopeId });
      if (requestVersion !== requestVersionRef.current) return;

      setData(next);
      setError(null);
      setStatus(next.status);

      if (shouldPoll(next.status)) {
        timerRef.current = setTimeout(() => void poll(), POLL_DELAY_MS);
      }
    } catch (caught) {
      if (requestVersion !== requestVersionRef.current) return;
      setError(caught);
      setStatus("idle");
    }
  }, [clearPollTimer, documentId, scopeId]);

  const refresh = useCallback(async () => {
    await poll();
  }, [poll]);

  useEffect(() => {
    setStatus(documentId ? "loading" : "idle");
    setData(null);
    setError(null);
    void poll();

    return () => {
      requestVersionRef.current += 1;
      clearPollTimer();
    };
  }, [clearPollTimer, documentId, poll]);

  return { status, data, error, refresh };
}
