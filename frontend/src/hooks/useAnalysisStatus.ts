import { useCallback, useEffect, useRef, useState } from "react";
import {
  type AnalysisStatus,
  getAnalysis,
  type TreatmentAnalysisRow,
} from "../api/treatments";

const INITIAL_POLL_DELAY_MS = 2_000;
const MAX_POLL_DELAY_MS = 10_000;

export type AnalysisHookStatus = AnalysisStatus | "idle" | "loading";

export type UseAnalysisStatusResult = {
  status: AnalysisHookStatus;
  data: TreatmentAnalysisRow | null;
  error: unknown;
  refresh: () => Promise<void>;
};

function shouldPoll(status: AnalysisHookStatus): boolean {
  return status === "pending" || status === "running";
}

function nextDelay(currentDelay: number): number {
  return Math.min(currentDelay * 2, MAX_POLL_DELAY_MS);
}

export function useAnalysisStatus(treatmentId: string): UseAnalysisStatusResult {
  const [data, setData] = useState<TreatmentAnalysisRow | null>(null);
  const [status, setStatus] = useState<AnalysisHookStatus>("loading");
  const [error, setError] = useState<unknown>(null);
  const delayRef = useRef(INITIAL_POLL_DELAY_MS);

  const refresh = useCallback(async () => {
    setError(null);
    const next = await getAnalysis(treatmentId);
    setData(next);
    setStatus(next?.status ?? "idle");
  }, [treatmentId]);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    async function poll(): Promise<void> {
      try {
        const next = await getAnalysis(treatmentId);
        if (cancelled) return;

        setData(next);
        setError(null);
        const nextStatus = next?.status ?? "idle";
        setStatus(nextStatus);

        if (shouldPoll(nextStatus)) {
          const delay = delayRef.current;
          delayRef.current = nextDelay(delay);
          timer = setTimeout(() => void poll(), delay);
        } else {
          delayRef.current = INITIAL_POLL_DELAY_MS;
        }
      } catch (caught) {
        if (cancelled) return;
        setError(caught);
        setStatus("idle");
        delayRef.current = INITIAL_POLL_DELAY_MS;
      }
    }

    setStatus("loading");
    setData(null);
    setError(null);
    delayRef.current = INITIAL_POLL_DELAY_MS;
    void poll();

    return () => {
      cancelled = true;
      if (timer !== null) clearTimeout(timer);
    };
  }, [treatmentId]);

  return { status, data, error, refresh };
}
