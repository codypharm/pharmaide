import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as treatmentsApi from "../../api/treatments";
import type {
  AdherenceEventList,
  TreatmentList,
  TreatmentListItem,
} from "../../api/treatments";
import AdherenceHeatmapsPage from "../AdherenceHeatmapsPage";

function treatmentRow(id: string, name: string, medication: string): TreatmentListItem {
  return {
    patient: {
      id: `patient-${id}`,
      name,
      dob: "1955-10-12",
      mrn: `MRN-${id}`,
      phone: "+18005551212",
      allergies: [],
    },
    treatment: {
      id,
      patient_id: `patient-${id}`,
      status: "active",
      chat_response_mode: "ai_active",
      automation_mode: "active",
      clinical_objective: "Monitor adherence",
      treatment_start_at: "2026-05-16T08:00:00Z",
      created_at: "2026-05-15T09:00:00Z",
    },
    medication_count: 1,
    first_medication_name: medication,
  };
}

function renderPage({ isPrivacyMode = false }: { isPrivacyMode?: boolean } = {}) {
  return render(
    <MemoryRouter initialEntries={["/dashboard/heatmaps"]}>
      <Routes>
        <Route element={<Outlet context={{ isPrivacyMode }} />}>
          <Route path="/dashboard/heatmaps" element={<AdherenceHeatmapsPage />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("AdherenceHeatmapsPage", () => {
  it("renders real treatments with adherence counts and recent events", async () => {
    const treatments: TreatmentList = {
      items: [
        treatmentRow("treatment-1", "Eleanor Vance", "Lisinopril"),
        treatmentRow("treatment-2", "Marcus Chen", "Metformin"),
      ],
    };
    const adherenceByTreatment: Record<string, AdherenceEventList> = {
      "treatment-1": {
        items: [
          {
            id: "event-1",
            treatment_id: "treatment-1",
            medication_id: "med-1",
            status: "taken",
            source: "patient",
            scheduled_for: isoDaysAgo(1),
            occurred_at: isoDaysAgo(1),
            note: null,
            created_at: isoDaysAgo(1),
          },
          {
            id: "event-2",
            treatment_id: "treatment-1",
            medication_id: "med-1",
            status: "missed",
            source: "patient",
            scheduled_for: isoDaysAgo(0),
            occurred_at: null,
            note: "Patient missed morning dose",
            created_at: isoDaysAgo(0),
          },
        ],
      },
      "treatment-2": { items: [] },
    };
    vi.spyOn(treatmentsApi, "listTreatments").mockResolvedValue(treatments);
    const adherenceSpy = vi
      .spyOn(treatmentsApi, "listAdherenceEvents")
      .mockImplementation((treatmentId) =>
        Promise.resolve(adherenceByTreatment[treatmentId] ?? { items: [] }),
      );

    renderPage();

    await screen.findByText("Eleanor Vance");
    expect(screen.getByText("Marcus Chen")).toBeTruthy();
    expect(screen.getByText("Lisinopril")).toBeTruthy();
    expect(screen.getAllByText("Taken").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Missed").length).toBeGreaterThan(0);
    expect(screen.getAllByText("1").length).toBeGreaterThan(1);
    expect(screen.getByText("Patient missed morning dose")).toBeTruthy();
    expect(adherenceSpy).toHaveBeenCalledWith("treatment-1");
    expect(adherenceSpy).toHaveBeenCalledWith("treatment-2");
  });

  it("filters adherence events when the date range changes", async () => {
    const user = userEvent.setup();
    vi.spyOn(treatmentsApi, "listTreatments").mockResolvedValue({
      items: [treatmentRow("treatment-1", "Eleanor Vance", "Lisinopril")],
    });
    vi.spyOn(treatmentsApi, "listAdherenceEvents").mockResolvedValue({
      items: [
        {
          id: "recent-event",
          treatment_id: "treatment-1",
          medication_id: "med-1",
          status: "taken",
          source: "patient",
          scheduled_for: isoDaysAgo(2),
          occurred_at: isoDaysAgo(2),
          note: "Recent taken dose",
          created_at: isoDaysAgo(2),
        },
        {
          id: "older-event",
          treatment_id: "treatment-1",
          medication_id: "med-1",
          status: "missed",
          source: "patient",
          scheduled_for: isoDaysAgo(20),
          occurred_at: null,
          note: "Older missed dose",
          created_at: isoDaysAgo(20),
        },
      ],
    });

    renderPage();

    await screen.findByText("Recent taken dose");
    expect(screen.getByText("Older missed dose")).toBeTruthy();

    await user.selectOptions(screen.getByLabelText(/adherence date range/i), "7");

    expect(screen.getByText("Recent taken dose")).toBeTruthy();
    expect(screen.queryByText("Older missed dose")).toBeNull();
  });

  it("shows an empty state when there are no treatments", async () => {
    vi.spyOn(treatmentsApi, "listTreatments").mockResolvedValue({ items: [] });

    renderPage();

    await screen.findByText(/no adherence data yet/i);
    expect(screen.getByText(/create a treatment before adherence tracking can start/i)).toBeTruthy();
  });

  it("blurs patient identifiers when privacy mode is active", async () => {
    vi.spyOn(treatmentsApi, "listTreatments").mockResolvedValue({
      items: [treatmentRow("treatment-1", "Eleanor Vance", "Lisinopril")],
    });
    vi.spyOn(treatmentsApi, "listAdherenceEvents").mockResolvedValue({ items: [] });

    renderPage({ isPrivacyMode: true });

    const name = await screen.findByText("Eleanor Vance");
    const mrn = screen.getByText("MRN-treatment-1");
    expect(name.className).toMatch(/blur-sm/);
    expect(mrn.className).toMatch(/blur-sm/);
  });
});

function isoDaysAgo(daysAgo: number): string {
  const date = new Date();
  date.setHours(8, 0, 0, 0);
  date.setDate(date.getDate() - daysAgo);
  return date.toISOString();
}
