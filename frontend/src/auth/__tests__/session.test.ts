import { afterEach, describe, expect, it, vi } from "vitest";

import { getJson, setAuthTokenProvider } from "../../api/client";
import { type FrontendConfig } from "../../config";
import { configureAuthSession } from "../session";

const DISABLED_CONFIG: FrontendConfig = {
  apiBaseUrl: "http://localhost:8000",
  authMode: "disabled",
  gcip: null,
};

const GCIP_CONFIG: FrontendConfig = {
  apiBaseUrl: "https://backend.example",
  authMode: "gcip",
  gcip: {
    apiKey: "api-key",
    authDomain: "pharmaide.example",
    projectId: "pharmaide-prod",
  },
};

function mockFetch() {
  return vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: new Headers({ "X-Request-ID": "req_auth" }),
    }),
  );
}

afterEach(() => {
  setAuthTokenProvider(null);
  vi.restoreAllMocks();
});

describe("configureAuthSession", () => {
  it("clears token provider when frontend auth is disabled", async () => {
    const fetchSpy = mockFetch();

    const state = configureAuthSession(DISABLED_CONFIG);
    await getJson("/treatments");

    expect(state).toEqual({ status: "disabled" });
    expect(fetchSpy.mock.calls[0][1]?.headers).toBeUndefined();
  });

  it("reports missing GCIP adapter without registering a token provider", async () => {
    const fetchSpy = mockFetch();

    const state = configureAuthSession(GCIP_CONFIG);
    await getJson("/treatments");

    expect(state).toEqual({ status: "missing_adapter", mode: "gcip" });
    expect(fetchSpy.mock.calls[0][1]?.headers).toBeUndefined();
  });

  it("registers GCIP adapter token provider for API requests", async () => {
    const fetchSpy = mockFetch();

    const state = configureAuthSession(GCIP_CONFIG, {
      getIdToken: () => "id-token-789",
    });
    await getJson("/treatments");

    expect(state).toEqual({ status: "ready", mode: "gcip" });
    expect(fetchSpy.mock.calls[0][1]?.headers).toEqual({
      Authorization: "Bearer id-token-789",
    });
  });
});
