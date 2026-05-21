import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  ConflictError,
  NotFoundError,
  UnauthorizedError,
  deleteJson,
  getText,
  getJson,
  postJson,
  postMultipart,
  setAuthTokenProvider,
  setUnauthorizedHandler,
} from "../client";

function mockFetch(response: {
  status: number;
  body: unknown;
  headers?: Record<string, string>;
}) {
  // mockImplementation (not mockResolvedValue) so each call gets a fresh
  // Response — Response bodies are streams and can only be read once.
  return vi.spyOn(globalThis, "fetch").mockImplementation(async () => {
    const headers = new Headers({ "X-Request-ID": "req_test_123", ...response.headers });
    return new Response(JSON.stringify(response.body), {
      status: response.status,
      headers,
    });
  });
}

afterEach(() => {
  setAuthTokenProvider(null);
  setUnauthorizedHandler(null);
  vi.restoreAllMocks();
});

describe("postJson", () => {
  it("returns the parsed body on 2xx", async () => {
    mockFetch({ status: 201, body: { treatment_id: "t1", patient_id: "p1" } });
    const result = await postJson("/treatments", { foo: "bar" });
    expect(result).toEqual({ treatment_id: "t1", patient_id: "p1" });
  });

  it("adds the current bearer token when an auth provider is registered", async () => {
    const fetchSpy = mockFetch({ status: 201, body: { ok: true } });
    setAuthTokenProvider(async () => "id-token-123");

    await postJson("/treatments", { foo: "bar" });

    const [, init] = fetchSpy.mock.calls[0];
    expect(init?.headers).toEqual({
      "Content-Type": "application/json",
      Authorization: "Bearer id-token-123",
    });
  });

  it("throws ValidationError on 422 with the field errors attached", async () => {
    mockFetch({
      status: 422,
      body: {
        detail: [
          { loc: ["body", "patient", "phone"], msg: "value is not a valid phone number", type: "value_error" },
        ],
      },
    });

    await expect(postJson("/treatments", {})).rejects.toMatchObject({
      status: 422,
      fieldErrors: [{ loc: ["body", "patient", "phone"], msg: expect.any(String), type: "value_error" }],
      requestId: "req_test_123",
    });
  });

  it("throws ConflictError on 409 with the error code", async () => {
    mockFetch({ status: 409, body: { detail: { error: "mrn_already_exists" } } });

    await expect(postJson("/treatments", {})).rejects.toThrow(ConflictError);
    try {
      await postJson("/treatments", {});
    } catch (err) {
      expect(err).toBeInstanceOf(ConflictError);
      expect((err as ConflictError).errorCode).toBe("mrn_already_exists");
      expect((err as ConflictError).requestId).toBe("req_test_123");
    }
  });

  it("throws UnauthorizedError on 401 with the auth error code", async () => {
    mockFetch({ status: 401, body: { detail: { error: "auth_token_required" } } });

    await expect(postJson("/treatments", {})).rejects.toThrow(UnauthorizedError);
    try {
      await postJson("/treatments", {});
    } catch (err) {
      expect(err).toBeInstanceOf(UnauthorizedError);
      expect((err as UnauthorizedError).errorCode).toBe("auth_token_required");
      expect((err as UnauthorizedError).requestId).toBe("req_test_123");
    }
  });
});

describe("getJson", () => {
  it("returns the parsed body on 2xx", async () => {
    mockFetch({ status: 200, body: { id: "t1", status: "pending" } });
    const result = await getJson("/treatments/t1");
    expect(result).toEqual({ id: "t1", status: "pending" });
  });

  it("throws NotFoundError on 404 with the error code", async () => {
    mockFetch({ status: 404, body: { detail: { error: "treatment_not_found" } } });

    await expect(getJson("/treatments/missing")).rejects.toThrow(NotFoundError);
    try {
      await getJson("/treatments/missing");
    } catch (err) {
      expect(err).toBeInstanceOf(NotFoundError);
      expect((err as NotFoundError).errorCode).toBe("treatment_not_found");
      expect((err as NotFoundError).requestId).toBe("req_test_123");
    }
  });

  it("throws ApiError on 500", async () => {
    mockFetch({ status: 500, body: { error: "internal_error" } });
    await expect(getJson("/treatments/x")).rejects.toThrow(ApiError);
  });

  it("throws UnauthorizedError on 401", async () => {
    mockFetch({ status: 401, body: { detail: { error: "invalid_auth_token" } } });

    await expect(getJson("/treatments")).rejects.toMatchObject({
      status: 401,
      errorCode: "invalid_auth_token",
    });
  });

  it("notifies the registered unauthorized handler on 401", async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    mockFetch({ status: 401, body: { detail: { error: "auth_token_required" } } });

    await expect(getJson("/treatments")).rejects.toThrow(UnauthorizedError);

    expect(handler).toHaveBeenCalledWith(
      expect.objectContaining({
        status: 401,
        errorCode: "auth_token_required",
      }),
    );
  });
});

describe("getText", () => {
  it("throws UnauthorizedError on 401", async () => {
    mockFetch({ status: 401, body: { detail: { error: "auth_token_required" } } });

    await expect(getText("/audits/export.csv")).rejects.toThrow(UnauthorizedError);
  });
});

describe("deleteJson", () => {
  it("sends DELETE and accepts an empty 204 response", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation(async () => {
      return new Response(null, {
        status: 204,
        headers: new Headers({ "X-Request-ID": "req_delete" }),
      });
    });

    await expect(
      deleteJson("/knowledge/documents/doc1", {
        headers: { "X-Pharmaide-User-Id": "scope1" },
      }),
    ).resolves.toBeNull();

    const [, init] = fetchSpy.mock.calls[0];
    expect(init?.method).toBe("DELETE");
    expect(init?.headers).toEqual({ "X-Pharmaide-User-Id": "scope1" });
  });
});

describe("postJson 500", () => {
  it("throws ApiError on 500 with request_id breadcrumb", async () => {
    mockFetch({
      status: 500,
      body: { error: "internal_error", request_id: "req_for_500" },
    });

    await expect(postJson("/treatments", {})).rejects.toThrow(ApiError);
    try {
      await postJson("/treatments", {});
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      expect((err as ApiError).status).toBe(500);
      expect((err as ApiError).requestId).toBe("req_test_123");
    }
  });
});

describe("postMultipart", () => {
  it("posts FormData without overriding the browser boundary content type", async () => {
    const fetchSpy = mockFetch({
      status: 200,
      body: { patient: {}, treatment: {}, medications: [], warnings: [] },
    });
    const form = new FormData();
    form.append("file", new File(["fake"], "script.png", { type: "image/png" }));

    const result = await postMultipart("/prescriptions/extract", form);

    expect(result).toEqual({ patient: {}, treatment: {}, medications: [], warnings: [] });
    const [, init] = fetchSpy.mock.calls[0];
    expect(init?.method).toBe("POST");
    expect(init?.body).toBe(form);
    expect(init?.headers).toBeUndefined();
  });

  it("accepts explicit headers without setting Content-Type", async () => {
    const fetchSpy = mockFetch({
      status: 202,
      body: { document_id: "doc1", status: "ingesting" },
    });
    const form = new FormData();
    form.append("file", new File(["fake"], "protocol.csv", { type: "text/csv" }));

    await postMultipart("/knowledge/documents", form, {
      headers: { "X-Pharmaide-User-Id": "scope1" },
    });

    const [, init] = fetchSpy.mock.calls[0];
    expect(init?.headers).toEqual({ "X-Pharmaide-User-Id": "scope1" });
  });

  it("merges bearer auth with explicit non-JSON headers", async () => {
    const fetchSpy = mockFetch({
      status: 202,
      body: { document_id: "doc1", status: "ingesting" },
    });
    setAuthTokenProvider(() => "id-token-456");
    const form = new FormData();
    form.append("file", new File(["fake"], "protocol.csv", { type: "text/csv" }));

    await postMultipart("/knowledge/documents", form, {
      headers: { "X-Pharmaide-User-Id": "scope1" },
    });

    const [, init] = fetchSpy.mock.calls[0];
    expect(init?.headers).toEqual({
      "X-Pharmaide-User-Id": "scope1",
      Authorization: "Bearer id-token-456",
    });
  });
});
