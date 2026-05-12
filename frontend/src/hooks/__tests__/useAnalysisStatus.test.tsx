import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { type AnalysisStatus, type TreatmentAnalysisRow } from "../../api/treatments";
import { useAnalysisStatus } from "../useAnalysisStatus";

function analysisRow(status: AnalysisStatus): TreatmentAnalysisRow {
  return {
    id: `analysis-${status}`,
    treatment_id: "treatment-1",
    status,
    result: null,
    error_text: null,
    started_at: "2026-05-12T10:00:00Z",
    completed_at: status === "completed" ? "2026-05-12T10:01:00Z" : null,
    created_at: "2026-05-12T10:00:00Z",
  };
}

function mockAnalysisResponses(responses: Array<TreatmentAnalysisRow | null>) {
  const fallback = responses.length > 0 ? responses[responses.length - 1] : analysisRow("completed");
  return vi.spyOn(globalThis, "fetch").mockImplementation(async () => {
    const next = responses.length > 0 ? responses.shift() : fallback;
    return new Response(JSON.stringify(next), {
      status: 200,
      headers: new Headers({ "X-Request-ID": "req_analysis" }),
    });
  });
}

function mockAnalysisFailure(error: Error) {
  return vi.spyOn(globalThis, "fetch").mockRejectedValue(error);
}

async function flushHookWork(): Promise<void> {
  await act(async () => {
    await Promise.resolve();
  });
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe("useAnalysisStatus", () => {
  it("polls active analysis and stops after a terminal status", async () => {
    const spy = mockAnalysisResponses([analysisRow("running"), analysisRow("completed")]);

    const { result } = renderHook(() => useAnalysisStatus("treatment-1"));

    await flushHookWork();
    expect(result.current.status).toBe("running");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2_000);
    });
    expect(result.current.status).toBe("completed");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });

    expect(spy).toHaveBeenCalledTimes(2);
  });

  it("keeps polling active analysis with an exponential delay cap", async () => {
    const spy = mockAnalysisResponses([analysisRow("running")]);

    const { result } = renderHook(() => useAnalysisStatus("treatment-1"));

    await flushHookWork();
    expect(result.current.status).toBe("running");
    expect(spy).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2_000);
    });
    expect(spy).toHaveBeenCalledTimes(2);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(4_000);
    });
    expect(spy).toHaveBeenCalledTimes(3);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(8_000);
    });
    expect(spy).toHaveBeenCalledTimes(4);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });
    expect(spy).toHaveBeenCalledTimes(5);
  });

  it("continues polling when manual refresh finds a pending analysis", async () => {
    const spy = mockAnalysisResponses([
      null,
      analysisRow("pending"),
      analysisRow("completed"),
    ]);

    const { result } = renderHook(() => useAnalysisStatus("treatment-1"));

    await flushHookWork();
    expect(result.current.status).toBe("idle");

    await act(async () => {
      await result.current.refresh();
    });
    expect(result.current.status).toBe("pending");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2_000);
    });
    expect(result.current.status).toBe("completed");
    expect(spy).toHaveBeenCalledTimes(3);
  });

  it("stops polling after an analysis load error", async () => {
    const error = new Error("network down");
    const spy = mockAnalysisFailure(error);

    const { result } = renderHook(() => useAnalysisStatus("treatment-1"));

    await flushHookWork();
    expect(result.current.status).toBe("idle");
    expect(result.current.error).toBe(error);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });

    expect(spy).toHaveBeenCalledTimes(1);
  });
});
