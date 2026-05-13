import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  PRE_AUTH_KB_SCOPE_ID,
  type KnowledgeDocumentStatus,
  type KnowledgeDocumentView,
} from "../../api/knowledge";
import { useDocumentIngestionStatus } from "../useDocumentIngestionStatus";

const SCOPE = { scopeId: PRE_AUTH_KB_SCOPE_ID };

function documentRow(status: KnowledgeDocumentStatus): KnowledgeDocumentView {
  return {
    id: "doc-1",
    title: "Formulary",
    mime: "text/csv",
    status,
    chunk_count: status === "ready" ? 12 : 0,
    created_at: "2026-05-13T10:00:00Z",
    updated_at: "2026-05-13T10:01:00Z",
  };
}

function mockDocumentResponses(responses: KnowledgeDocumentView[]) {
  const fallback = responses.length > 0 ? responses[responses.length - 1] : documentRow("ready");
  return vi.spyOn(globalThis, "fetch").mockImplementation(async () => {
    const next = responses.length > 0 ? responses.shift() : fallback;
    return new Response(JSON.stringify(next), {
      status: 200,
      headers: new Headers({ "X-Request-ID": "req_kb" }),
    });
  });
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

describe("useDocumentIngestionStatus", () => {
  it("polls while a document is ingesting and stops at ready", async () => {
    const spy = mockDocumentResponses([documentRow("ingesting"), documentRow("ready")]);

    const { result } = renderHook(() => useDocumentIngestionStatus("doc-1", SCOPE));

    await flushHookWork();
    expect(result.current.status).toBe("ingesting");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(3_000);
    });
    expect(result.current.status).toBe("ready");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(9_000);
    });

    expect(spy).toHaveBeenCalledTimes(2);
  });

  it("does not poll when no document id is provided", async () => {
    const spy = vi.spyOn(globalThis, "fetch");

    const { result } = renderHook(() => useDocumentIngestionStatus(null, SCOPE));

    await flushHookWork();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3_000);
    });

    expect(result.current.status).toBe("idle");
    expect(spy).not.toHaveBeenCalled();
  });

  it("stops polling after a load error", async () => {
    const error = new Error("network down");
    const spy = vi.spyOn(globalThis, "fetch").mockRejectedValue(error);

    const { result } = renderHook(() => useDocumentIngestionStatus("doc-1", SCOPE));

    await flushHookWork();
    expect(result.current.status).toBe("idle");
    expect(result.current.error).toBe(error);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(9_000);
    });

    expect(spy).toHaveBeenCalledTimes(1);
  });
});
