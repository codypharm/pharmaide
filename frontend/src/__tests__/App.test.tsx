import { render, screen } from "@testing-library/react";
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

  it("blurs patient names when privacy mode is toggled on", async () => {
    const user = await openDashboard();
    await user.click(screen.getByRole("link", { name: /^surveillance$/i }));

    const name = await screen.findByText("Thomas Miller");
    expect(name.className).not.toMatch(/blur-sm/);

    await user.click(screen.getByLabelText("Privacy Mode"));

    expect(name.className).toMatch(/blur-sm/);
  });
});
