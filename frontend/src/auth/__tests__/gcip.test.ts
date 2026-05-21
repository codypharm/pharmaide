import { afterEach, describe, expect, it, vi } from "vitest";

import { createGcipAuthAdapter } from "../gcip";

type MockUser = { email: string; getIdToken: () => Promise<string> };
type MockApp = { name: string };

const mocks = vi.hoisted(() => {
  const authState = {
    currentUser: {
      email: "pharmacist@example.com",
      getIdToken: vi.fn(async () => "id-token-123"),
    } as MockUser | null,
  };
  return {
    authState,
    initializeApp: vi.fn((): MockApp => ({ name: "pharmaide" })),
    getApp: vi.fn((): MockApp => ({ name: "pharmaide" })),
    getApps: vi.fn((): MockApp[] => []),
    getAuth: vi.fn(() => authState),
    signInWithEmailAndPassword: vi.fn(async () => undefined),
    signOut: vi.fn(async () => undefined),
  };
});

vi.mock("firebase/app", () => ({
  initializeApp: mocks.initializeApp,
  getApp: mocks.getApp,
  getApps: mocks.getApps,
}));

vi.mock("firebase/auth", () => ({
  getAuth: mocks.getAuth,
  signInWithEmailAndPassword: mocks.signInWithEmailAndPassword,
  signOut: mocks.signOut,
}));

afterEach(() => {
  mocks.authState.currentUser = {
    email: "pharmacist@example.com",
    getIdToken: vi.fn(async () => "id-token-123"),
  };
  vi.clearAllMocks();
});

describe("createGcipAuthAdapter", () => {
  it("initializes Firebase with browser-safe GCIP config", () => {
    createGcipAuthAdapter({
      apiKey: "api-key",
      authDomain: "pharmaide.example",
      projectId: "pharmaide-prod",
    });

    expect(mocks.initializeApp).toHaveBeenCalledWith(
      {
        apiKey: "api-key",
        authDomain: "pharmaide.example",
        projectId: "pharmaide-prod",
      },
      "pharmaide",
    );
    expect(mocks.getAuth).toHaveBeenCalledWith({ name: "pharmaide" });
  });

  it("reuses an existing named Firebase app", () => {
    mocks.getApps.mockReturnValueOnce([{ name: "pharmaide" }]);

    createGcipAuthAdapter({
      apiKey: "api-key",
      authDomain: "pharmaide.example",
      projectId: "pharmaide-prod",
    });

    expect(mocks.getApp).toHaveBeenCalledWith("pharmaide");
    expect(mocks.initializeApp).not.toHaveBeenCalled();
  });

  it("returns the current user's ID token for API requests", async () => {
    const adapter = createGcipAuthAdapter({
      apiKey: "api-key",
      authDomain: "pharmaide.example",
      projectId: "pharmaide-prod",
    });

    await expect(adapter.getIdToken()).resolves.toBe("id-token-123");
  });

  it("returns null when no user is signed in", async () => {
    mocks.authState.currentUser = null;
    const adapter = createGcipAuthAdapter({
      apiKey: "api-key",
      authDomain: "pharmaide.example",
      projectId: "pharmaide-prod",
    });

    await expect(adapter.getIdToken()).resolves.toBeNull();
    expect(adapter.currentUserEmail()).toBeNull();
  });

  it("supports email/password sign-in and sign-out", async () => {
    const adapter = createGcipAuthAdapter({
      apiKey: "api-key",
      authDomain: "pharmaide.example",
      projectId: "pharmaide-prod",
    });

    await adapter.signInWithEmailPassword("pharmacist@example.com", "secret");
    await adapter.signOut();

    expect(mocks.signInWithEmailAndPassword).toHaveBeenCalledWith(
      mocks.authState,
      "pharmacist@example.com",
      "secret",
    );
    expect(mocks.signOut).toHaveBeenCalledWith(mocks.authState);
  });
});
