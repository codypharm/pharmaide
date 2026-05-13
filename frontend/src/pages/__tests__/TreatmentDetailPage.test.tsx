import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import TreatmentDetailPage from "../TreatmentDetailPage";
import { ApiError, NotFoundError } from "../../api/client";
import * as treatmentsApi from "../../api/treatments";
import type { TreatmentAnalysisRow, TreatmentDetail } from "../../api/treatments";

const SAMPLE: TreatmentDetail = {
  patient: {
    id: "11111111-1111-1111-1111-111111111111",
    name: "Eleanor Vance",
    dob: "1955-10-12",
    mrn: "PHA-AB12CD34",
    phone: "+18005551212",
  },
  treatment: {
    id: "22222222-2222-2222-2222-222222222222",
    patient_id: "11111111-1111-1111-1111-111111111111",
    status: "pending",
    clinical_objective: "Monitor for cough",
    created_at: "2026-05-11T12:00:00Z",
  },
  medications: [
    {
      id: "33333333-3333-3333-3333-333333333333",
      name: "Lisinopril",
      dosage: "10 mg",
      frequency: "Once Daily (QD)",
      duration: "30 days",
      objective: null,
      ordinal: 0,
    },
  ],
};

const COMPLETED_ANALYSIS: TreatmentAnalysisRow = {
  id: "44444444-4444-4444-4444-444444444444",
  treatment_id: SAMPLE.treatment.id,
  status: "completed",
  result: {
    groundings: [
      {
        medication_id: SAMPLE.medications[0].id,
        medication_name: "Lisinopril",
        rxcui: "29046",
        normalized_name: "lisinopril",
        confidence: 0.93,
      },
    ],
    ddi_warnings: [
      {
        medication_ids: [
          SAMPLE.medications[0].id,
          "55555555-5555-5555-5555-555555555555",
        ],
        severity: "major",
        description: "Monitor INR closely.",
        source: "licensed-provider",
      },
    ],
    schedule: {
      reminders: Array.from({ length: 21 }, (_, index) => ({
        medication_id: SAMPLE.medications[0].id,
        offset_from_start: `PT${index + 1}H`,
        human_label: `Day 1, ${String(index + 1).padStart(2, "0")}:00`,
      })),
    },
    kb_citations: [
      {
        chunk_id: "77777777-7777-7777-7777-777777777777",
        document_id: "88888888-8888-8888-8888-888888888888",
        document_title: "Clinic Hypertension Protocol",
        source_uri: "local://kb/hypertension.pdf",
        text: "ACE inhibitors require monitoring for cough and dizziness.",
        score: 0.91,
      },
    ],
    reasoning: {
      summary: "Patient should be monitored for cough and dizziness.",
      red_flags: ["Escalate worsening dizziness."],
      confidence: 0.84,
    },
    degraded: false,
    partial_results: false,
    completed_stages: [
      "ground_medications",
      "check_interactions",
      "generate_schedule",
      "summarize_treatment",
    ],
  },
  error_text: null,
  started_at: "2026-05-12T10:00:00Z",
  completed_at: "2026-05-12T10:01:00Z",
  created_at: "2026-05-12T10:00:00Z",
};

const RUNNING_ANALYSIS: TreatmentAnalysisRow = {
  ...COMPLETED_ANALYSIS,
  id: "66666666-6666-6666-6666-666666666666",
  status: "running",
  result: null,
  completed_at: null,
};

function renderAt(treatmentId: string, { isPrivacyMode = false }: { isPrivacyMode?: boolean } = {}) {
  // TreatmentDetailPage reads isPrivacyMode via useOutletContext, so it must
  // be rendered as a nested route under a parent that supplies the context.
  return render(
    <MemoryRouter initialEntries={[`/dashboard/treatments/${treatmentId}`]}>
      <Routes>
        <Route element={<Outlet context={{ isPrivacyMode }} />}>
          <Route path="/dashboard/treatments/:id" element={<TreatmentDetailPage />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("TreatmentDetailPage", () => {
  it("shows a loading placeholder while fetching", () => {
    // Promise that never resolves — we just want to observe the loading frame.
    vi.spyOn(treatmentsApi, "getTreatment").mockImplementation(
      () => new Promise(() => {}),
    );

    renderAt(SAMPLE.treatment.id);

    expect(screen.getByText(/loading treatment/i)).toBeTruthy();
  });

  it("renders patient, treatment, and medications on success", async () => {
    vi.spyOn(treatmentsApi, "getTreatment").mockResolvedValue(SAMPLE);

    renderAt(SAMPLE.treatment.id);

    await waitFor(() => expect(screen.getByText("Eleanor Vance")).toBeTruthy());
    expect(screen.getByText("PHA-AB12CD34")).toBeTruthy();
    expect(screen.getByText("+18005551212")).toBeTruthy();
    expect(screen.getByText("Monitor for cough")).toBeTruthy();
    expect(screen.getByText("Lisinopril")).toBeTruthy();
    expect(screen.getByText("10 mg")).toBeTruthy();
  });

  it("shows a 'not found' empty state when the treatment is missing", async () => {
    vi.spyOn(treatmentsApi, "getTreatment").mockRejectedValue(
      new NotFoundError("req_x", { detail: { error: "treatment_not_found" } }, "treatment_not_found"),
    );

    renderAt(SAMPLE.treatment.id);

    await waitFor(() => expect(screen.getByText(/treatment not found/i)).toBeTruthy());
  });

  it("blurs all PHI fields when privacy mode is on", async () => {
    vi.spyOn(treatmentsApi, "getTreatment").mockResolvedValue(SAMPLE);

    renderAt(SAMPLE.treatment.id, { isPrivacyMode: true });

    const name = await screen.findByText("Eleanor Vance");
    const mrn = screen.getByText("PHA-AB12CD34");
    const phone = screen.getByText("+18005551212");
    expect(name.className).toMatch(/blur-sm/);
    expect(mrn.className).toMatch(/blur-sm/);
    expect(phone.className).toMatch(/blur-sm/);
  });

  it("shows a generic error state with the request id on other failures", async () => {
    vi.spyOn(treatmentsApi, "getTreatment").mockRejectedValue(
      new ApiError(500, "req_500", { error: "internal_error" }, "Request failed: 500"),
    );

    renderAt(SAMPLE.treatment.id);

    await waitFor(() => expect(screen.getByText(/could not load/i)).toBeTruthy());
    expect(screen.getByText(/req_500/)).toBeTruthy();
  });

  it("lets the pharmacist start analysis from the Reasoning tab", async () => {
    vi.spyOn(treatmentsApi, "getTreatment").mockResolvedValue(SAMPLE);
    vi.spyOn(treatmentsApi, "getAnalysis").mockResolvedValue(null);
    const trigger = vi
      .spyOn(treatmentsApi, "triggerAnalysis")
      .mockResolvedValue({ analysis_id: "analysis-1" });
    const user = userEvent.setup();

    renderAt(SAMPLE.treatment.id);

    await screen.findByText("Eleanor Vance");
    const reasoningTab = screen.getByRole("tab", { name: /reasoning/i });
    expect(reasoningTab).toHaveClass("cursor-pointer");
    expect(reasoningTab).toHaveAttribute("aria-selected", "false");

    await user.click(reasoningTab);

    expect(reasoningTab).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText(/no analysis has been run/i)).toBeTruthy();

    await user.click(screen.getByRole("button", { name: /run analysis/i }));

    expect(trigger).toHaveBeenCalledWith(SAMPLE.treatment.id);
  });

  it("renders completed analysis results in the Reasoning tab", async () => {
    vi.spyOn(treatmentsApi, "getTreatment").mockResolvedValue(SAMPLE);
    vi.spyOn(treatmentsApi, "getAnalysis").mockResolvedValue(COMPLETED_ANALYSIS);
    const user = userEvent.setup();

    renderAt(SAMPLE.treatment.id);

    await screen.findByText("Eleanor Vance");
    await user.click(screen.getByRole("tab", { name: /reasoning/i }));

    expect(
      await screen.findByText("Patient should be monitored for cough and dizziness."),
    ).toBeTruthy();
    expect(screen.getByText("Escalate worsening dizziness.")).toBeTruthy();
    expect(screen.getByText("Sources")).toBeTruthy();
    expect(screen.getByText("Clinic Hypertension Protocol")).toBeTruthy();
    expect(screen.getByText("Relevance 91%")).toBeTruthy();
    expect(
      screen.getByText("ACE inhibitors require monitoring for cough and dizziness."),
    ).toBeTruthy();
    expect(screen.getAllByText(/Lisinopril/).length).toBeGreaterThan(1);
    expect(screen.getByText(/RxCUI 29046/)).toBeTruthy();
    expect(screen.getByText("Monitor INR closely.")).toBeTruthy();
    expect(screen.getByText("Reminder 1")).toBeTruthy();
    expect(screen.getAllByText("Lisinopril").length).toBeGreaterThan(0);
    expect(screen.getByText(/planned relative schedule/i)).toBeTruthy();
    expect(screen.getByText("Day 1, 01:00")).toBeTruthy();
    expect(screen.getByText("Planned Day 1 · +1h")).toBeTruthy();
    expect(screen.getByText("Day 1, 20:00")).toBeTruthy();
    expect(screen.getByText("Day 1, 21:00")).toBeTruthy();
  });

  it("lets the pharmacist confirm a forced re-run after an analysis exists", async () => {
    vi.spyOn(treatmentsApi, "getTreatment").mockResolvedValue(SAMPLE);
    vi.spyOn(treatmentsApi, "getAnalysis").mockResolvedValue(COMPLETED_ANALYSIS);
    const trigger = vi
      .spyOn(treatmentsApi, "triggerAnalysis")
      .mockResolvedValue({ analysis_id: "analysis-rerun" });
    const user = userEvent.setup();

    renderAt(SAMPLE.treatment.id);

    await screen.findByText("Eleanor Vance");
    await user.click(screen.getByRole("tab", { name: /reasoning/i }));
    await screen.findByText("Patient should be monitored for cough and dizziness.");

    await user.click(screen.getByRole("button", { name: /^re-run$/i }));
    expect(screen.getByText(/replace the current analysis/i)).toBeTruthy();

    await user.click(screen.getByRole("button", { name: /confirm re-run/i }));

    expect(trigger).toHaveBeenCalledWith(SAMPLE.treatment.id, { force: true });
  });

  it("does not show re-run while analysis is still running", async () => {
    vi.spyOn(treatmentsApi, "getTreatment").mockResolvedValue(SAMPLE);
    vi.spyOn(treatmentsApi, "getAnalysis").mockResolvedValue(RUNNING_ANALYSIS);
    const user = userEvent.setup();

    renderAt(SAMPLE.treatment.id);

    await screen.findByText("Eleanor Vance");
    await user.click(screen.getByRole("tab", { name: /reasoning/i }));

    expect(await screen.findByText("running")).toBeTruthy();
    expect(screen.getByText(/analysis in progress/i)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /^re-run$/i })).toBeNull();
  });
});
