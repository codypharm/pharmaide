import { describe, expect, it } from "vitest";

import { getFrontendConfig } from "../config";

describe("frontend config", () => {
  it("defaults to local API and disabled auth", () => {
    expect(getFrontendConfig({})).toEqual({
      apiBaseUrl: "http://localhost:8000",
      authMode: "disabled",
      gcip: null,
    });
  });

  it("reads deployed API URL and GCIP settings", () => {
    expect(
      getFrontendConfig({
        VITE_API_BASE_URL: "https://backend.example",
        VITE_AUTH_MODE: "gcip",
        VITE_GCIP_API_KEY: "api-key",
        VITE_GCIP_AUTH_DOMAIN: "pharmaide.example",
        VITE_GCIP_PROJECT_ID: "pharmaide-prod",
      }),
    ).toEqual({
      apiBaseUrl: "https://backend.example",
      authMode: "gcip",
      gcip: {
        apiKey: "api-key",
        authDomain: "pharmaide.example",
        projectId: "pharmaide-prod",
      },
    });
  });

  it("rejects GCIP mode when required browser env is missing", () => {
    expect(() => getFrontendConfig({ VITE_AUTH_MODE: "gcip" })).toThrow(
      /GCIP auth requires/,
    );
  });

  it("rejects unknown auth modes", () => {
    expect(() => getFrontendConfig({ VITE_AUTH_MODE: "magic" })).toThrow(
      /Unsupported frontend auth mode/,
    );
  });
});
