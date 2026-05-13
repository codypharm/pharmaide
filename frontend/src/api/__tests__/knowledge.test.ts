import { afterEach, describe, expect, it, vi } from "vitest";
import {
  deleteKnowledgeDocument,
  getKnowledgeDocument,
  listKnowledgeDocuments,
  uploadKnowledgeDocument,
} from "../knowledge";

function mockFetch(response: { status: number; body: unknown }) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = typeof input === "string" ? input : (input as Request).url;
    const body =
      response.status === 204
        ? null
        : JSON.stringify({ ...(response.body as object), _url: url, _method: init?.method });
    return new Response(body, {
      status: response.status,
      headers: new Headers({ "X-Request-ID": "req_kb" }),
    });
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("uploadKnowledgeDocument", () => {
  it("uploads the file as multipart with the explicit KB scope header", async () => {
    const spy = mockFetch({ status: 202, body: { document_id: "doc1", status: "ingesting" } });
    const file = new File(["drug,dose\nWarfarin,5 mg"], "formulary.csv", {
      type: "text/csv",
    });

    const result = await uploadKnowledgeDocument(file, { scopeId: "scope-123" });

    const calledUrl = spy.mock.calls[0]?.[0] as string;
    const init = spy.mock.calls[0]?.[1] as RequestInit;
    expect(calledUrl).toMatch(/\/knowledge\/documents$/);
    expect(init.method).toBe("POST");
    expect(init.body).toBeInstanceOf(FormData);
    expect(init.headers).toEqual({ "X-Pharmaide-User-Id": "scope-123" });
    expect(result).toEqual({
      document_id: "doc1",
      status: "ingesting",
      _url: expect.any(String),
      _method: "POST",
    });
  });
});

describe("listKnowledgeDocuments", () => {
  it("passes pagination and the explicit KB scope header", async () => {
    const spy = mockFetch({
      status: 200,
      body: {
        items: [
          {
            id: "doc1",
            source_type: "user_upload",
            title: "Anticoagulation Protocol",
            mime: "application/pdf",
            status: "ready",
            chunk_count: 4,
            created_at: "2026-05-13T10:00:00Z",
            updated_at: "2026-05-13T10:01:00Z",
          },
        ],
      },
    });

    const result = await listKnowledgeDocuments({
      scopeId: "scope-123",
      limit: 25,
      offset: 50,
    });

    const calledUrl = spy.mock.calls[0]?.[0] as string;
    const init = spy.mock.calls[0]?.[1] as RequestInit;
    expect(calledUrl).toContain("/knowledge/documents?");
    expect(calledUrl).toContain("limit=25");
    expect(calledUrl).toContain("offset=50");
    expect(init.headers).toEqual({ "X-Pharmaide-User-Id": "scope-123" });
    expect(result.items[0].chunk_count).toBe(4);
  });
});

describe("getKnowledgeDocument", () => {
  it("loads one document by id", async () => {
    const spy = mockFetch({
      status: 200,
      body: {
        id: "doc1",
        source_type: "user_upload",
        title: "Anticoagulation Protocol",
        mime: "application/pdf",
        status: "ready",
        chunk_count: 4,
        created_at: "2026-05-13T10:00:00Z",
        updated_at: "2026-05-13T10:01:00Z",
      },
    });

    const result = await getKnowledgeDocument("doc1", { scopeId: "scope-123" });

    const calledUrl = spy.mock.calls[0]?.[0] as string;
    expect(calledUrl).toMatch(/\/knowledge\/documents\/doc1$/);
    expect(result.title).toBe("Anticoagulation Protocol");
  });
});

describe("deleteKnowledgeDocument", () => {
  it("soft-deletes one document by id", async () => {
    const spy = mockFetch({ status: 204, body: null });

    await deleteKnowledgeDocument("doc1", { scopeId: "scope-123" });

    const calledUrl = spy.mock.calls[0]?.[0] as string;
    const init = spy.mock.calls[0]?.[1] as RequestInit;
    expect(calledUrl).toMatch(/\/knowledge\/documents\/doc1$/);
    expect(init.method).toBe("DELETE");
    expect(init.headers).toEqual({ "X-Pharmaide-User-Id": "scope-123" });
  });
});
