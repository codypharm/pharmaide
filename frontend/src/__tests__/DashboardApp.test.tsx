import { useEffect } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import DashboardApp from "../DashboardApp";
import { getJson, setUnauthorizedHandler } from "../api/client";

function UnauthorizedProbe() {
  useEffect(() => {
    void getJson("/treatments").catch(() => undefined);
  }, []);

  return <div>Protected content</div>;
}

afterEach(() => {
  setUnauthorizedHandler(null);
  vi.restoreAllMocks();
});

describe("DashboardApp auth state", () => {
  it("shows a session alert when an API request is unauthorized", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: { error: "auth_token_required" } }), {
        status: 401,
        headers: new Headers({ "X-Request-ID": "req_auth_123" }),
      }),
    );

    render(
      <MemoryRouter initialEntries={["/dashboard/protected"]}>
        <Routes>
          <Route path="/dashboard" element={<DashboardApp />}>
            <Route path="protected" element={<UnauthorizedProbe />} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Session needs attention. Sign in again to continue.",
    );
    expect(screen.getByText(/req_auth_123/i)).toBeInTheDocument();
  });

  it("blocks protected content when GCIP is enabled without a sign-in adapter", () => {
    render(
      <MemoryRouter initialEntries={["/dashboard/protected"]}>
        <Routes>
          <Route
            path="/dashboard"
            element={
              <DashboardApp authSessionState={{ status: "missing_adapter", mode: "gcip" }} />
            }
          >
            <Route path="protected" element={<div>Protected content</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByRole("alert")).toHaveTextContent("GCIP sign-in is not connected.");
    expect(screen.queryByText("Protected content")).not.toBeInTheDocument();
  });

  it("shows protected content after GCIP email sign-in succeeds", async () => {
    const user = userEvent.setup();
    let signedInEmail: string | null = null;
    const adapter = {
      getIdToken: vi.fn(() => (signedInEmail ? "id-token-123" : null)),
      signInWithEmailPassword: vi.fn(async (email: string) => {
        signedInEmail = email;
      }),
      currentUserEmail: vi.fn(() => signedInEmail),
    };

    render(
      <MemoryRouter initialEntries={["/dashboard/protected"]}>
        <Routes>
          <Route
            path="/dashboard"
            element={
              <DashboardApp authSessionState={{ status: "ready", mode: "gcip", adapter }} />
            }
          >
            <Route path="protected" element={<div>Protected content</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText("Sign in to PharmaAide")).toBeInTheDocument();
    expect(screen.queryByText("Protected content")).not.toBeInTheDocument();

    await user.type(screen.getByLabelText(/email/i), "pharmacist@example.com");
    await user.type(screen.getByLabelText(/password/i), "correct-password");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect(adapter.signInWithEmailPassword).toHaveBeenCalledWith(
      "pharmacist@example.com",
      "correct-password",
    );
    expect(await screen.findByText("Protected content")).toBeInTheDocument();
  });

  it("returns to the GCIP sign-in gate after sign-out", async () => {
    const user = userEvent.setup();
    let signedInEmail: string | null = "pharmacist@example.com";
    const adapter = {
      getIdToken: vi.fn(() => (signedInEmail ? "id-token-123" : null)),
      signInWithEmailPassword: vi.fn(async (email: string) => {
        signedInEmail = email;
      }),
      signOut: vi.fn(async () => {
        signedInEmail = null;
      }),
      currentUserEmail: vi.fn(() => signedInEmail),
    };

    render(
      <MemoryRouter initialEntries={["/dashboard/protected"]}>
        <Routes>
          <Route
            path="/dashboard"
            element={
              <DashboardApp authSessionState={{ status: "ready", mode: "gcip", adapter }} />
            }
          >
            <Route path="protected" element={<div>Protected content</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText("Protected content")).toBeInTheDocument();
    expect(screen.getAllByText("pharmacist@example.com").length).toBeGreaterThan(0);
    expect(screen.getByText("GCIP active")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /sign out/i }));

    expect(adapter.signOut).toHaveBeenCalled();
    expect(await screen.findByText("Sign in to PharmaAide")).toBeInTheDocument();
    expect(screen.queryByText("Protected content")).not.toBeInTheDocument();
  });

  it("returns GCIP users to the sign-in gate after an unauthorized API response", async () => {
    let signedInEmail: string | null = "pharmacist@example.com";
    const adapter = {
      getIdToken: vi.fn(() => (signedInEmail ? "expired-token" : null)),
      signInWithEmailPassword: vi.fn(async (email: string) => {
        signedInEmail = email;
      }),
      signOut: vi.fn(async () => {
        signedInEmail = null;
      }),
      currentUserEmail: vi.fn(() => signedInEmail),
    };
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: { error: "invalid_auth_token" } }), {
        status: 401,
        headers: new Headers({ "X-Request-ID": "req_expired_123" }),
      }),
    );

    render(
      <MemoryRouter initialEntries={["/dashboard/protected"]}>
        <Routes>
          <Route
            path="/dashboard"
            element={
              <DashboardApp authSessionState={{ status: "ready", mode: "gcip", adapter }} />
            }
          >
            <Route path="protected" element={<UnauthorizedProbe />} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText("Protected content")).toBeInTheDocument();

    expect(await screen.findByText("Sign in to PharmaAide")).toBeInTheDocument();
    expect(adapter.signOut).toHaveBeenCalled();
    expect(screen.queryByText("Protected content")).not.toBeInTheDocument();
    expect(screen.getByText(/req_expired_123/i)).toBeInTheDocument();
  });
});
