import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import * as treatmentsApi from "../api/treatments";
import type { TreatmentList } from "../api/treatments";

const SURVEILLANCE_TREATMENTS: TreatmentList = {
  items: [
    {
      patient: {
        id: "patient-1",
        name: "Thomas Miller",
        dob: "1954-03-10",
        mrn: "PHA-TM01",
        phone: "+18005550101",
        allergies: [],
      },
      treatment: {
        id: "88340000-0000-4000-8000-000000000001",
        patient_id: "patient-1",
        status: "pending",
        chat_response_mode: "ai_active",
        automation_mode: "active",
        clinical_objective: "Monitor dizziness",
        treatment_start_at: null,
        created_at: "2026-05-15T10:00:00Z",
      },
      medication_count: 1,
      first_medication_name: "Lisinopril",
    },
  ],
};

beforeEach(() => {
  // App uses BrowserRouter which reads window.location. jsdom persists
  // location across tests, so a previous navigation would leave the
  // dashboard mounted instead of the landing page. Reset to "/" each test.
  window.history.pushState({}, "", "/");
  vi.spyOn(treatmentsApi, "listTreatments").mockResolvedValue(SURVEILLANCE_TREATMENTS);
  vi.spyOn(treatmentsApi, "listConversationMessages").mockResolvedValue({ items: [] });
});

afterEach(() => {
  vi.restoreAllMocks();
});

async function openDashboard() {
  const user = userEvent.setup();
  render(<App />);
  await user.click(screen.getAllByRole("button", { name: /review triage/i })[0]);
  return user;
}

describe("PharmaAide app shell", () => {
  it("renders the public landing page first", () => {
    render(<App />);

    expect(screen.getByRole("heading", { level: 1, name: /pharmaaide keeps/i })).toBeTruthy();
    expect(screen.getAllByRole("button", { name: /review triage/i }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("button", { name: /open surveillance/i }).length).toBeGreaterThan(0);
    // Dashboard chrome should not be present yet.
    expect(screen.queryByRole("link", { name: /surveillance/i })).not.toBeInTheDocument();
  });

  it("uses a sign-in CTA on the landing page when GCIP auth is enabled", () => {
    render(
      <App
        authSessionState={{
          status: "ready",
          mode: "gcip",
          adapter: {
            getIdToken: () => null,
            currentUserEmail: () => null,
          },
        }}
      />,
    );

    expect(screen.getAllByRole("button", { name: /sign in/i }).length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: /review triage/i })).not.toBeInTheDocument();
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
    expect(await screen.findByText("Thomas Miller")).toBeTruthy();
    expect(screen.getAllByText("88340000").length).toBeGreaterThan(0);
  });

  it("shows the signed-in pharmacist in dashboard chrome and profile", async () => {
    window.history.pushState({}, "", "/dashboard/profile");
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          actor_id: "11111111-1111-4111-8111-111111111111",
          subject: "firebase-user-123",
          auth_mode: "gcip",
          email: "pharmacist@example.com",
          workspace_id: "22222222-2222-4222-8222-222222222222",
          kb_scope_id: "22222222-2222-4222-8222-222222222222",
        }),
        {
          status: 200,
          headers: new Headers({ "X-Request-ID": "req_auth_me" }),
        },
      ),
    );

    render(
      <App
        authSessionState={{
          status: "ready",
          mode: "gcip",
          adapter: {
            getIdToken: () => "id-token",
            currentUserEmail: () => "pharmacist@example.com",
          },
        }}
      />,
    );

    expect(screen.getAllByText("pharmacist@example.com").length).toBeGreaterThan(0);
    expect(screen.getAllByText("GCIP session active").length).toBeGreaterThan(0);
    expect(await screen.findByText("Server-verified identity")).toBeInTheDocument();
    expect(screen.getAllByText("Workspace verified").length).toBeGreaterThan(0);
  });

  it("hides patient names when privacy mode is toggled on", async () => {
    const user = await openDashboard();
    await user.click(screen.getByRole("link", { name: /^surveillance$/i }));

    expect(await screen.findByText("Thomas Miller")).toBeTruthy();

    await user.click(screen.getByLabelText("Privacy Mode"));

    await waitFor(() => {
      expect(screen.getAllByText("Patient hidden").length).toBeGreaterThan(0);
    });
    expect(screen.queryByText("Thomas Miller")).not.toBeInTheDocument();
  });
});
