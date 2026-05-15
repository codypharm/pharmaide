import { afterEach, describe, expect, it, vi } from "vitest";

import { approveTriageItem, listTriageItems, updateTriageItemStatus } from "../triage";

function mockFetch(response: { status: number; body: unknown }) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = typeof input === "string" ? input : (input as Request).url;
    return new Response(
      JSON.stringify({ ...(response.body as object), _url: url, _method: init?.method }),
      {
        status: response.status,
        headers: new Headers({ "X-Request-ID": "req_triage" }),
      },
    );
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("listTriageItems", () => {
  it("loads triage items with pagination", async () => {
    const spy = mockFetch({
      status: 200,
      body: {
        items: [
          {
            id: "triage-1",
            treatment_id: "treatment-1",
            conversation_message_id: "message-1",
            reason: "referee",
            status: "open",
            created_at: "2026-05-15T10:00:00Z",
          },
        ],
      },
    });

    const result = await listTriageItems({ limit: 25, offset: 50 });

    const calledUrl = spy.mock.calls[0]?.[0] as string;
    expect(calledUrl).toContain("/triage/items?");
    expect(calledUrl).toContain("limit=25");
    expect(calledUrl).toContain("offset=50");
    expect(result.items[0].reason).toBe("referee");
  });
});

describe("updateTriageItemStatus", () => {
  it("patches a triage item status", async () => {
    const spy = mockFetch({
      status: 200,
      body: {
        id: "triage-1",
        treatment_id: "treatment-1",
        conversation_message_id: null,
        reason: "output_guard",
        status: "acknowledged",
        created_at: "2026-05-15T10:00:00Z",
      },
    });

    const result = await updateTriageItemStatus("triage-1", "acknowledged");

    const calledUrl = spy.mock.calls[0]?.[0] as string;
    const init = spy.mock.calls[0]?.[1] as RequestInit;
    expect(calledUrl).toMatch(/\/triage\/items\/triage-1$/);
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(String(init.body))).toEqual({ status: "acknowledged" });
    expect(result.status).toBe("acknowledged");
  });
});

describe("approveTriageItem", () => {
  it("posts to the triage approve endpoint", async () => {
    const spy = mockFetch({
      status: 200,
      body: {
        triage_item: {
          id: "triage-1",
          treatment_id: "treatment-1",
          conversation_message_id: "message-1",
          reason: "referee",
          status: "resolved",
          created_at: "2026-05-15T10:00:00Z",
        },
        approved_message: {
          id: "message-1",
          treatment_id: "treatment-1",
          direction: "outbound",
          sender_type: "assistant",
          channel: "whatsapp",
          status: "approved",
          body: "Please continue as prescribed.",
          safety_hold_reason: "referee",
          external_message_id: null,
          created_at: "2026-05-15T10:01:00Z",
        },
      },
    });

    const result = await approveTriageItem("triage-1");

    const calledUrl = spy.mock.calls[0]?.[0] as string;
    const init = spy.mock.calls[0]?.[1] as RequestInit;
    expect(calledUrl).toMatch(/\/triage\/items\/triage-1\/approve$/);
    expect(init.method).toBe("POST");
    expect(result.triage_item.status).toBe("resolved");
    expect(result.approved_message.status).toBe("approved");
  });
});
