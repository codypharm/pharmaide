import { useEffect } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
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
});
