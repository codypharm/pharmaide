import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import App from "../App";

beforeEach(() => {
  // App uses BrowserRouter which reads window.location. jsdom persists
  // location across tests, so a previous navigation would leave the
  // dashboard mounted instead of the landing page. Reset to "/" each test.
  window.history.pushState({}, "", "/");
});

async function openDashboard() {
  const user = userEvent.setup();
  render(<App />);
  await user.click(screen.getByRole("button", { name: "Get Started" }));
  return user;
}

describe("PharmaAide app shell", () => {
  it("renders the public landing page first", () => {
    render(<App />);

    expect(screen.getByRole("heading", { level: 1 })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Get Started" })).toBeTruthy();
    // Dashboard chrome should not be present yet.
    expect(screen.queryByRole("link", { name: /surveillance/i })).not.toBeInTheDocument();
  });

  it("navigates into the dashboard when Get Started is clicked", async () => {
    await openDashboard();

    expect(screen.getAllByText("PharmaAide").length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: /triage queue/i })).toBeTruthy();
    expect(screen.getByRole("link", { name: /^surveillance$/i })).toBeTruthy();
    expect(screen.getByRole("link", { name: /^adherence$/i })).toBeTruthy();
  });

  it("opens the patient surveillance roster from the sidebar", async () => {
    const user = await openDashboard();
    await user.click(screen.getByRole("link", { name: /^surveillance$/i }));

    expect(screen.getByText("Patient Directory")).toBeTruthy();
    expect(screen.getByText("Thomas Miller")).toBeTruthy();
    expect(screen.getByText("P-8834")).toBeTruthy();
  });

  it("blurs patient names when privacy mode is toggled on", async () => {
    const user = await openDashboard();
    await user.click(screen.getByRole("link", { name: /^surveillance$/i }));

    const name = screen.getByText("Thomas Miller");
    expect(name.className).not.toMatch(/blur-sm/);

    await user.click(screen.getByLabelText("Privacy Mode"));

    expect(name.className).toMatch(/blur-sm/);
  });
});
