import { afterEach, describe, expect, it, vi } from "vitest";
import { getAnalysis, listTreatments, triggerAnalysis } from "../treatments";

function mockFetch(response: { status: number; body: unknown }) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = typeof input === "string" ? input : (input as Request).url;
    const body =
      response.status === 204
        ? null
        : JSON.stringify({ ...(response.body as object), _url: url });
    return new Response(body, {
      status: response.status,
      headers: new Headers({ "X-Request-ID": "req_test" }),
    });
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("listTreatments", () => {
  it("calls /treatments with no query params by default", async () => {
    const spy = mockFetch({ status: 200, body: { items: [] } });
    await listTreatments();

    const calledUrl = spy.mock.calls[0]?.[0] as string;
    expect(calledUrl).toMatch(/\/treatments$/);
  });

  it("passes limit and offset through as query params", async () => {
    const spy = mockFetch({ status: 200, body: { items: [] } });
    await listTreatments({ limit: 25, offset: 50 });

    const calledUrl = spy.mock.calls[0]?.[0] as string;
    expect(calledUrl).toContain("limit=25");
    expect(calledUrl).toContain("offset=50");
  });

  it("returns the parsed items array on success", async () => {
    mockFetch({
      status: 200,
      body: {
        items: [
          {
            patient: {
              id: "p1",
              name: "Eleanor",
              dob: "1955-10-12",
              mrn: "M1",
              phone: "+1",
              allergies: [],
            },
            treatment: {
              id: "t1",
              patient_id: "p1",
              status: "pending",
              clinical_objective: null,
              treatment_start_at: null,
              created_at: "2026-05-11T12:00:00Z",
            },
            medication_count: 2,
            first_medication_name: "Lisinopril",
          },
        ],
      },
    });

    const result = await listTreatments();
    expect(result.items).toHaveLength(1);
    expect(result.items[0].medication_count).toBe(2);
    expect(result.items[0].first_medication_name).toBe("Lisinopril");
  });
});

describe("triggerAnalysis", () => {
  it("posts to the treatment analysis endpoint", async () => {
    const spy = mockFetch({ status: 202, body: { analysis_id: "a1" } });

    const result = await triggerAnalysis("t1");

    const calledUrl = spy.mock.calls[0]?.[0] as string;
    const init = spy.mock.calls[0]?.[1] as RequestInit;
    expect(calledUrl).toMatch(/\/treatments\/t1\/analyze$/);
    expect(init.method).toBe("POST");
    expect(result.analysis_id).toBe("a1");
  });

  it("passes force=true when rerunning an analysis", async () => {
    const spy = mockFetch({ status: 202, body: { analysis_id: "a2" } });

    await triggerAnalysis("t1", { force: true });

    const calledUrl = spy.mock.calls[0]?.[0] as string;
    expect(calledUrl).toContain("/treatments/t1/analyze?force=true");
  });
});

describe("getAnalysis", () => {
  it("returns null when the backend has no analysis row yet", async () => {
    mockFetch({ status: 204, body: null });

    await expect(getAnalysis("t1")).resolves.toBeNull();
  });

  it("returns the latest analysis row with typed partial-result fields", async () => {
    mockFetch({
      status: 200,
      body: {
        id: "a1",
        treatment_id: "t1",
        status: "failed",
        result: {
          groundings: [],
          ddi_warnings: [],
          schedule: null,
          reasoning: null,
          degraded: true,
          partial_results: true,
          completed_stages: ["ground_medications"],
        },
        error_text: "analysis_failed",
        started_at: "2026-05-12T10:00:00Z",
        completed_at: "2026-05-12T10:01:00Z",
        created_at: "2026-05-12T10:00:00Z",
      },
    });

    const result = await getAnalysis("t1");

    expect(result?.status).toBe("failed");
    expect(result?.result?.partial_results).toBe(true);
    expect(result?.result?.completed_stages).toEqual(["ground_medications"]);
  });
});
