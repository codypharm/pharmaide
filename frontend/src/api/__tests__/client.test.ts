import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  ConflictError,
  NotFoundError,
  deleteJson,
  getJson,
  postJson,
  postMultipart,
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
  vi.restoreAllMocks();
});

describe("postJson", () => {
  it("returns the parsed body on 2xx", async () => {
    mockFetch({ status: 201, body: { treatment_id: "t1", patient_id: "p1" } });
    const result = await postJson("/treatments", { foo: "bar" });
    expect(result).toEqual({ treatment_id: "t1", patient_id: "p1" });
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
});
