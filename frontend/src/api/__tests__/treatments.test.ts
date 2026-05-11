import { afterEach, describe, expect, it, vi } from "vitest";
import { listTreatments } from "../treatments";

function mockFetch(response: { status: number; body: unknown }) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = typeof input === "string" ? input : (input as Request).url;
    return new Response(JSON.stringify({ ...(response.body as object), _url: url }), {
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
            patient: { id: "p1", name: "Eleanor", dob: "1955-10-12", mrn: "M1", phone: "+1" },
            treatment: { id: "t1", patient_id: "p1", status: "pending", clinical_objective: null, created_at: "2026-05-11T12:00:00Z" },
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
