import { afterEach, describe, expect, it, vi } from "vitest";

import { listAuditLogEntries } from "../audits";

function mockFetch(response: { status: number; body: unknown }) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = typeof input === "string" ? input : (input as Request).url;
    return new Response(
      JSON.stringify({ ...(response.body as object), _url: url, _method: init?.method }),
      {
        status: response.status,
        headers: new Headers({ "X-Request-ID": "req_audit" }),
      },
    );
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("listAuditLogEntries", () => {
  it("loads audit log entries with pagination", async () => {
    const spy = mockFetch({
      status: 200,
      body: {
        items: [
          {
            id: "audit-1",
            actor_id: null,
            event_type: "analysis_started",
            resource_type: "treatment",
            resource_id: "treatment-1",
            payload: { medication_count: 2 },
            created_at: "2026-05-15T10:00:00Z",
          },
        ],
      },
    });

    const result = await listAuditLogEntries({ limit: 25, offset: 50 });

    const calledUrl = spy.mock.calls[0]?.[0] as string;
    expect(calledUrl).toContain("/audits?");
    expect(calledUrl).toContain("limit=25");
    expect(calledUrl).toContain("offset=50");
    expect(result.items[0].event_type).toBe("analysis_started");
  });
});
