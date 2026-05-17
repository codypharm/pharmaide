import { afterEach, describe, expect, it, vi } from "vitest";

import { searchPatients } from "../patients";

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

describe("searchPatients", () => {
  it("passes query, limit, and offset to /patients", async () => {
    const spy = mockFetch({ status: 200, body: { items: [] } });

    await searchPatients({ query: "Eleanor", limit: 10, offset: 20 });

    const calledUrl = spy.mock.calls[0]?.[0] as string;
    expect(calledUrl).toMatch(/\/patients\?/);
    expect(calledUrl).toContain("query=Eleanor");
    expect(calledUrl).toContain("limit=10");
    expect(calledUrl).toContain("offset=20");
  });

  it("returns matching patient rows", async () => {
    mockFetch({
      status: 200,
      body: {
        items: [
          {
            id: "patient-1",
            name: "Eleanor Vance",
            dob: "1955-10-12",
            mrn: "PAT-001",
            phone: "+18005550101",
            allergies: ["Sulfa"],
          },
        ],
      },
    });

    const result = await searchPatients({ query: "PAT-001" });

    expect(result.items).toHaveLength(1);
    expect(result.items[0].name).toBe("Eleanor Vance");
    expect(result.items[0].allergies).toEqual(["Sulfa"]);
  });
});
