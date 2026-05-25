import { afterEach, describe, expect, it, vi } from "vitest";

import { setAuthTokenProvider } from "../client";
import { getCurrentActor } from "../auth";

function mockFetch(body: unknown) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async () => {
    return new Response(JSON.stringify(body), {
      status: 200,
      headers: new Headers({ "X-Request-ID": "req_auth_me" }),
    });
  });
}

afterEach(() => {
  setAuthTokenProvider(null);
  vi.restoreAllMocks();
});

describe("getCurrentActor", () => {
  it("loads the server-verified actor from /auth/me", async () => {
    const fetchSpy = mockFetch({
      actor_id: "11111111-1111-4111-8111-111111111111",
      subject: "firebase-user-123",
      auth_mode: "gcip",
      email: "pharmacist@example.com",
      workspace_id: "22222222-2222-4222-8222-222222222222",
      kb_scope_id: "22222222-2222-4222-8222-222222222222",
    });
    setAuthTokenProvider(() => "id-token");

    const actor = await getCurrentActor();

    expect(actor.email).toBe("pharmacist@example.com");
    expect(actor.workspace_id).toBe("22222222-2222-4222-8222-222222222222");
    expect(fetchSpy).toHaveBeenCalledWith(
      "http://localhost:8000/auth/me",
      expect.objectContaining({
        method: "GET",
        headers: { Authorization: "Bearer id-token" },
      }),
    );
  });
});
