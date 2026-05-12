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
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const requestVersionRef = useRef(0);

  const clearPollTimer = useCallback(() => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const poll = useCallback(
    async (resetDelay = false) => {
      clearPollTimer();
      if (resetDelay) {
        delayRef.current = INITIAL_POLL_DELAY_MS;
      }

      const requestVersion = ++requestVersionRef.current;
      try {
        const next = await getAnalysis(treatmentId);
        if (requestVersion !== requestVersionRef.current) return;

        setData(next);
        setError(null);
        const nextStatus = next?.status ?? "idle";
        setStatus(nextStatus);

        if (shouldPoll(nextStatus)) {
          const delay = delayRef.current;
          delayRef.current = nextDelay(delay);
          timerRef.current = setTimeout(() => void poll(), delay);
        } else {
          delayRef.current = INITIAL_POLL_DELAY_MS;
        }
      } catch (caught) {
        if (requestVersion !== requestVersionRef.current) return;
        setError(caught);
        setStatus("idle");
        delayRef.current = INITIAL_POLL_DELAY_MS;
      }
    },
    [clearPollTimer, treatmentId],
  );

  const refresh = useCallback(async () => {
    await poll(true);
  }, [poll]);

  useEffect(() => {
    setStatus("loading");
    setData(null);
    setError(null);
    delayRef.current = INITIAL_POLL_DELAY_MS;
    void poll(true);

    return () => {
      requestVersionRef.current += 1;
      clearPollTimer();
    };
  }, [clearPollTimer, poll]);

  return { status, data, error, refresh };
}
