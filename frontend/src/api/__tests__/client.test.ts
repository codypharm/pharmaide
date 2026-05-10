import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, ConflictError, postJson } from "../client";

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
