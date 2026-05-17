import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import TreatmentDetailPage from "../TreatmentDetailPage";
import { ApiError, NotFoundError } from "../../api/client";
import * as treatmentsApi from "../../api/treatments";
import type {
  AdherenceEventView,
  CourseCompletionReport,
  PatientCheckInView,
  TreatmentAnalysisRow,
  TreatmentDetail,
} from "../../api/treatments";

const SAMPLE: TreatmentDetail = {
  patient: {
    id: "11111111-1111-1111-1111-111111111111",
    name: "Eleanor Vance",
    dob: "1955-10-12",
    mrn: "PHA-AB12CD34",
    phone: "+18005551212",
    allergies: ["Penicillin", "Sulfa"],
  },
  treatment: {
    id: "22222222-2222-2222-2222-222222222222",
    patient_id: "11111111-1111-1111-1111-111111111111",
    status: "pending",
    chat_response_mode: "ai_active",
    automation_mode: "active",
    clinical_objective: "Monitor for cough",
    treatment_start_at: "2026-05-16T08:30:00Z",
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
        source_type: "user_upload",
        document_title: "Clinic Hypertension Protocol",
        source_uri: "local://kb/hypertension.pdf",
        text: "ACE inhibitors require monitoring for cough and dizziness.",
        score: 0.91,
      },
      {
        chunk_id: "99999999-9999-9999-9999-999999999999",
        document_id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        source_type: "dailymed",
        document_title: "Lisinopril Tablet",
        source_uri: "dailymed://setid-1",
        text: "DailyMed label includes dizziness warnings.",
        score: 0.83,
      },
    ],
    clinical_safety_review: {
      source_type: "model_review",
      possible_interactions: ["AI review suggests checking dizziness risk."],
      monitoring_concerns: ["Monitor blood pressure and dizziness."],
      counseling_points: ["Ask patient to report fainting."],
      missing_information: ["Recent blood pressure readings unavailable."],
      confidence: 0.72,
      requires_pharmacist_review: true,
    },
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

const FAILED_WITH_LAST_COMPLETED_ANALYSIS: TreatmentAnalysisRow = {
  ...COMPLETED_ANALYSIS,
  id: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
  status: "failed",
  result: null,
  error_text: "analysis_timeout",
  last_completed: COMPLETED_ANALYSIS,
};

const SAMPLE_CHECK_INS: PatientCheckInView[] = [
  {
    id: "check-in-1",
    treatment_id: SAMPLE.treatment.id,
    report_type: "not_improving",
    source: "patient",
    message: "I am not feeling better after three days.",
    observed_at: "2026-05-18T09:15:00Z",
    created_at: "2026-05-18T10:00:00Z",
  },
];

const SAMPLE_ADHERENCE_EVENTS: AdherenceEventView[] = [
  {
    id: "adherence-1",
    treatment_id: SAMPLE.treatment.id,
    medication_id: SAMPLE.medications[0].id,
    status: "taken",
    source: "patient",
    scheduled_for: "2026-05-16T09:30:00.000Z",
    occurred_at: "2026-05-16T09:35:00Z",
    note: null,
    created_at: "2026-05-16T09:35:00Z",
  },
];

const SAMPLE_COMPLETION_REPORT: CourseCompletionReport = {
  treatment_id: SAMPLE.treatment.id,
  patient_id: SAMPLE.patient.id,
  status: "completed",
  treatment_start_at: SAMPLE.treatment.treatment_start_at,
  created_at: SAMPLE.treatment.created_at,
  medication_count: 1,
  adherence: {
    total_count: 3,
    by_status: {
      taken: 2,
      missed: 1,
    },
  },
  patient_updates: {
    total_count: 2,
    by_report_type: {
      not_improving: 1,
      side_effect: 1,
    },
  },
  triage: {
    total_count: 1,
    by_status: {
      resolved: 1,
    },
    by_reason: {
      side_effect: 1,
    },
  },
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

beforeEach(() => {
  vi.spyOn(treatmentsApi, "listPatientCheckIns").mockResolvedValue({ items: [] });
  vi.spyOn(treatmentsApi, "listAdherenceEvents").mockResolvedValue({ items: [] });
  vi.spyOn(treatmentsApi, "getAnalysis").mockResolvedValue(null);
  vi.spyOn(treatmentsApi, "getCompletionReport").mockResolvedValue(SAMPLE_COMPLETION_REPORT);
});

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
    expect(screen.getByText("Penicillin")).toBeTruthy();
    expect(screen.getByText("Sulfa")).toBeTruthy();
    expect(screen.getByText(/May 16, 2026/i)).toBeTruthy();
    expect(screen.getByText("Monitor for cough")).toBeTruthy();
    expect(screen.getByText("Lisinopril")).toBeTruthy();
    expect(screen.getByText("10 mg")).toBeTruthy();
    expect(screen.getByText(/report available after course completion/i)).toBeTruthy();
    expect(treatmentsApi.getCompletionReport).not.toHaveBeenCalled();
    expect(await screen.findByText(/no patient-reported updates recorded/i)).toBeTruthy();
    expect(screen.getByRole("link", { name: /back/i })).toHaveAttribute(
      "href",
      "/dashboard/ingestions",
    );
  });

  it("lets the pharmacist start the treatment cycle", async () => {
    vi.spyOn(treatmentsApi, "getTreatment").mockResolvedValue(SAMPLE);
    vi.spyOn(treatmentsApi, "getAnalysis").mockResolvedValue(COMPLETED_ANALYSIS);
    const startCycle = vi.spyOn(treatmentsApi, "startTreatmentCycle").mockResolvedValue({
      ...SAMPLE.treatment,
      status: "active",
    });
    const user = userEvent.setup();

    renderAt(SAMPLE.treatment.id);

    await screen.findByText("Eleanor Vance");
    await user.click(screen.getByRole("button", { name: /start cycle/i }));

    expect(startCycle).toHaveBeenCalledWith(SAMPLE.treatment.id);
    expect(await screen.findByRole("button", { name: /stop monitoring/i })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /start cycle/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /cycle active/i })).toBeNull();
  });

  it("lets the pharmacist stop monitoring for an active treatment", async () => {
    const activeTreatment = { ...SAMPLE.treatment, status: "active" };
    vi.spyOn(treatmentsApi, "getTreatment").mockResolvedValue({
      ...SAMPLE,
      treatment: activeTreatment,
    });
    const terminate = vi.spyOn(treatmentsApi, "terminateTreatment").mockResolvedValue({
      ...activeTreatment,
      status: "terminated",
      automation_mode: "paused",
    });
    const user = userEvent.setup();

    renderAt(SAMPLE.treatment.id);

    await screen.findByText("Eleanor Vance");
    await user.click(screen.getByRole("button", { name: /stop monitoring/i }));
    expect(screen.getByText(/end this monitoring cycle/i)).toBeTruthy();
    await user.click(screen.getByRole("button", { name: /confirm stop/i }));

    expect(terminate).toHaveBeenCalledWith(SAMPLE.treatment.id);
    expect(await screen.findByText("Terminated")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /monitoring stopped/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /stop monitoring/i })).toBeNull();
  });

  it("does not show stop monitoring before the cycle is active", async () => {
    vi.spyOn(treatmentsApi, "getTreatment").mockResolvedValue(SAMPLE);
    vi.spyOn(treatmentsApi, "getAnalysis").mockResolvedValue(COMPLETED_ANALYSIS);

    renderAt(SAMPLE.treatment.id);

    await screen.findByText("Eleanor Vance");
    expect(screen.getByRole("button", { name: /start cycle/i })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /stop monitoring/i })).toBeNull();
  });

  it("does not show the stop monitoring action after course completion", async () => {
    vi.spyOn(treatmentsApi, "getTreatment").mockResolvedValue({
      ...SAMPLE,
      treatment: { ...SAMPLE.treatment, status: "completed" },
    });
    vi.spyOn(treatmentsApi, "getAnalysis").mockResolvedValue(COMPLETED_ANALYSIS);

    renderAt(SAMPLE.treatment.id);

    await screen.findByText("Eleanor Vance");
    expect(screen.queryByRole("button", { name: /stop monitoring/i })).toBeNull();
  });

  it("lets the pharmacist discontinue a medication on an active treatment", async () => {
    const activeTreatment = { ...SAMPLE.treatment, status: "active" };
    vi.spyOn(treatmentsApi, "getTreatment")
      .mockResolvedValueOnce({
        ...SAMPLE,
        treatment: activeTreatment,
      })
      .mockResolvedValueOnce({
        ...SAMPLE,
        treatment: {
          ...activeTreatment,
          status: "terminated",
          automation_mode: "paused",
        },
        medications: [
          {
            ...SAMPLE.medications[0],
            discontinued_at: "2026-05-17T18:45:00Z",
          },
        ],
      });
    const discontinue = vi.spyOn(treatmentsApi, "discontinueMedication").mockResolvedValue({
      ...SAMPLE.medications[0],
      discontinued_at: "2026-05-17T18:45:00Z",
    });
    const user = userEvent.setup();

    renderAt(SAMPLE.treatment.id);

    await screen.findByText("Eleanor Vance");
    await user.click(screen.getByRole("button", { name: /^discontinue$/i }));
    await user.click(screen.getByRole("button", { name: /^confirm$/i }));

    expect(discontinue).toHaveBeenCalledWith(SAMPLE.treatment.id, SAMPLE.medications[0].id);
    expect(await screen.findByText("Discontinued")).toBeTruthy();
    expect(screen.getByText("Terminated")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /^discontinue$/i })).toBeNull();
  });

  it("lets the pharmacist discontinue a medication before cycle start", async () => {
    vi.spyOn(treatmentsApi, "getTreatment")
      .mockResolvedValueOnce({
        ...SAMPLE,
        medications: [
          SAMPLE.medications[0],
          {
            ...SAMPLE.medications[0],
            id: "77777777-7777-7777-7777-777777777777",
            name: "Amlodipine",
            ordinal: 1,
          },
        ],
      })
      .mockResolvedValueOnce({
        ...SAMPLE,
        treatment: {
          ...SAMPLE.treatment,
          status: "pending",
          automation_mode: "paused",
        },
        medications: [
          {
            ...SAMPLE.medications[0],
            discontinued_at: "2026-05-17T18:45:00Z",
          },
          {
            ...SAMPLE.medications[0],
            id: "77777777-7777-7777-7777-777777777777",
            name: "Amlodipine",
            ordinal: 1,
          },
        ],
      });
    const discontinue = vi.spyOn(treatmentsApi, "discontinueMedication").mockResolvedValue({
      ...SAMPLE.medications[0],
      discontinued_at: "2026-05-17T18:45:00Z",
    });
    const user = userEvent.setup();

    renderAt(SAMPLE.treatment.id);

    await screen.findByText("Eleanor Vance");
    await user.click(screen.getAllByRole("button", { name: /^discontinue$/i })[0]);
    await user.click(screen.getByRole("button", { name: /^confirm$/i }));

    expect(discontinue).toHaveBeenCalledWith(SAMPLE.treatment.id, SAMPLE.medications[0].id);
    expect(await screen.findByText("Discontinued")).toBeTruthy();
    expect(screen.getByText(/treatment plan changed/i)).toBeTruthy();
  });

  it("lets the pharmacist add a medication and pauses cycle start for analysis rerun", async () => {
    const activeTreatment = { ...SAMPLE.treatment, status: "active" };
    const addedMedication = {
      ...SAMPLE.medications[0],
      id: "88888888-8888-8888-8888-888888888888",
      name: "Amlodipine",
      dosage: "5 mg",
      ordinal: 1,
    };
    vi.spyOn(treatmentsApi, "getTreatment")
      .mockResolvedValueOnce({
        ...SAMPLE,
        treatment: activeTreatment,
      })
      .mockResolvedValueOnce({
        ...SAMPLE,
        treatment: {
          ...activeTreatment,
          status: "pending",
          automation_mode: "paused",
        },
        medications: [...SAMPLE.medications, addedMedication],
      });
    const addMedication = vi
      .spyOn(treatmentsApi, "addMedicationToTreatment")
      .mockResolvedValue(addedMedication);
    vi.spyOn(treatmentsApi, "getAnalysis").mockResolvedValue(COMPLETED_ANALYSIS);
    const user = userEvent.setup();

    renderAt(SAMPLE.treatment.id);

    await screen.findByText("Eleanor Vance");
    await user.click(screen.getByRole("button", { name: /add medication/i }));
    await user.type(screen.getByLabelText(/^medication name$/i), "Amlodipine");
    await user.type(screen.getByLabelText(/^dosage strength$/i), "5 mg");
    const frequencyInput = screen.getByLabelText(/^frequency$/i);
    expect(frequencyInput).toHaveAttribute("list", "frequency-suggestions");
    expect(
      document.querySelector('datalist#frequency-suggestions option[value="Twice Daily (BID)"]'),
    ).not.toBeNull();
    await user.type(frequencyInput, "Once Daily (QD)");
    await user.type(screen.getByLabelText(/^duration$/i), "30 days");
    await user.click(screen.getByRole("button", { name: /^save medication$/i }));

    expect(addMedication).toHaveBeenCalledWith(SAMPLE.treatment.id, {
      name: "Amlodipine",
      dosage: "5 mg",
      frequency: "Once Daily (QD)",
      duration: "30 days",
      objective: null,
    });
    expect(await screen.findByText("Amlodipine")).toBeTruthy();
    expect(screen.getByText(/treatment plan changed/i)).toBeTruthy();
    expect(screen.getByText(/rerun analysis before monitoring can resume/i)).toBeTruthy();
    expect(screen.getByRole("button", { name: /start cycle/i })).toBeDisabled();
  });

  it("lets the pharmacist update the treatment objective", async () => {
    vi.spyOn(treatmentsApi, "getTreatment").mockResolvedValue(SAMPLE);
    const updateObjective = vi
      .spyOn(treatmentsApi, "updateTreatmentClinicalObjective")
      .mockResolvedValue({
        ...SAMPLE.treatment,
        clinical_objective: "Monitor dizziness and cough",
      });
    const user = userEvent.setup();

    renderAt(SAMPLE.treatment.id);

    await screen.findByText("Eleanor Vance");
    const objective = screen.getByLabelText(/^treatment objective$/i);
    fireEvent.change(objective, { target: { value: "Monitor dizziness and cough" } });
    await user.click(screen.getByRole("button", { name: /save objective/i }));

    expect(updateObjective).toHaveBeenCalledWith(SAMPLE.treatment.id, {
      clinical_objective: "Monitor dizziness and cough",
    });
    expect(await screen.findByDisplayValue("Monitor dizziness and cough")).toBeTruthy();
  });

  it("disables cycle start until analysis is completed", async () => {
    vi.spyOn(treatmentsApi, "getTreatment").mockResolvedValue(SAMPLE);
    vi.spyOn(treatmentsApi, "getAnalysis").mockResolvedValue(RUNNING_ANALYSIS);

    renderAt(SAMPLE.treatment.id);

    await screen.findByText("Eleanor Vance");
    expect(await screen.findByRole("button", { name: /start cycle/i })).toBeDisabled();
    expect(screen.getByText(/complete analysis before starting cycle/i)).toBeTruthy();
  });

  it("shows completed treatments without offering cycle start", async () => {
    vi.spyOn(treatmentsApi, "getTreatment").mockResolvedValue({
      ...SAMPLE,
      treatment: { ...SAMPLE.treatment, status: "completed" },
    });
    vi.spyOn(treatmentsApi, "getAnalysis").mockResolvedValue(COMPLETED_ANALYSIS);

    renderAt(SAMPLE.treatment.id);

    await screen.findByText("Eleanor Vance");
    expect(screen.getByText("Completed")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /course completed/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /^start cycle$/i })).toBeNull();
  });

  it("shows that analysis must be rerun after a medication change pauses monitoring", async () => {
    vi.spyOn(treatmentsApi, "getTreatment").mockResolvedValue({
      ...SAMPLE,
      treatment: {
        ...SAMPLE.treatment,
        status: "pending",
        automation_mode: "paused",
      },
      medications: [
        {
          ...SAMPLE.medications[0],
          discontinued_at: "2026-05-17T18:45:00Z",
        },
        {
          ...SAMPLE.medications[0],
          id: "77777777-7777-7777-7777-777777777777",
          name: "Amlodipine",
          ordinal: 1,
        },
      ],
    });

    renderAt(SAMPLE.treatment.id);

    await screen.findByText("Eleanor Vance");
    expect(screen.getByText(/treatment plan changed/i)).toBeTruthy();
    expect(screen.getByText(/rerun analysis before monitoring can resume/i)).toBeTruthy();
  });

  it("clears the medication-change warning after newer analysis is completed", async () => {
    vi.spyOn(treatmentsApi, "getTreatment").mockResolvedValue({
      ...SAMPLE,
      treatment: {
        ...SAMPLE.treatment,
        status: "pending",
        automation_mode: "paused",
      },
      medications: [
        {
          ...SAMPLE.medications[0],
          discontinued_at: "2026-05-17T18:45:00Z",
        },
        {
          ...SAMPLE.medications[0],
          id: "77777777-7777-7777-7777-777777777777",
          name: "Amlodipine",
          ordinal: 1,
        },
      ],
    });
    vi.spyOn(treatmentsApi, "getAnalysis").mockResolvedValue({
      ...COMPLETED_ANALYSIS,
      completed_at: "2026-05-18T09:00:00Z",
    });

    renderAt(SAMPLE.treatment.id);

    await screen.findByText("Eleanor Vance");
    expect(screen.queryByText(/treatment plan changed/i)).toBeNull();
    expect(await screen.findByRole("button", { name: /start cycle/i })).toBeEnabled();
  });

  it("loads the completion report only after the pharmacist opens it", async () => {
    vi.spyOn(treatmentsApi, "getTreatment").mockResolvedValue({
      ...SAMPLE,
      treatment: { ...SAMPLE.treatment, status: "completed" },
    });
    const getCompletionReport = vi
      .spyOn(treatmentsApi, "getCompletionReport")
      .mockResolvedValue(SAMPLE_COMPLETION_REPORT);
    const user = userEvent.setup();

    renderAt(SAMPLE.treatment.id);

    await screen.findByText("Eleanor Vance");
    expect(screen.getByText("Course complete")).toBeTruthy();
    expect(getCompletionReport).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: /view completion report/i }));

    expect(getCompletionReport).toHaveBeenCalledWith(SAMPLE.treatment.id);
    expect(await screen.findByText("Course Completion Report")).toBeTruthy();
    expect(screen.getByText("1 medication")).toBeTruthy();
    expect(screen.getByText("2 taken")).toBeTruthy();
    expect(screen.getByText("1 missed")).toBeTruthy();
    expect(screen.getByText("2 patient updates")).toBeTruthy();
    expect(screen.getByText("1 triage item")).toBeTruthy();
  });

  it("lets the pharmacist archive a completed course", async () => {
    const archivedAt = "2026-05-20T12:00:00Z";
    vi.spyOn(treatmentsApi, "getTreatment").mockResolvedValue({
      ...SAMPLE,
      treatment: { ...SAMPLE.treatment, status: "completed", archived_at: null },
    });
    const archiveTreatment = vi.spyOn(treatmentsApi, "archiveTreatment").mockResolvedValue({
      ...SAMPLE.treatment,
      status: "completed",
      archived_at: archivedAt,
    });
    const user = userEvent.setup();

    renderAt(SAMPLE.treatment.id);

    await screen.findByText("Course complete");
    await user.click(screen.getByRole("button", { name: /archive completed course/i }));

    expect(archiveTreatment).toHaveBeenCalledWith(SAMPLE.treatment.id);
    expect(await screen.findByText(/archived may 20, 2026/i)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /archive completed course/i })).toBeNull();
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

  it("renders patient-reported updates on the overview tab", async () => {
    vi.spyOn(treatmentsApi, "getTreatment").mockResolvedValue(SAMPLE);
    vi.spyOn(treatmentsApi, "listPatientCheckIns").mockResolvedValue({
      items: SAMPLE_CHECK_INS,
    });

    renderAt(SAMPLE.treatment.id);

    expect(await screen.findByText("I am not feeling better after three days.")).toBeTruthy();
    expect(screen.getAllByText("Not improving").length).toBeGreaterThan(0);
    expect(screen.getByText("Source: Patient")).toBeTruthy();
  });

  it("lets the pharmacist record a patient-reported clinical update", async () => {
    vi.spyOn(treatmentsApi, "getTreatment").mockResolvedValue(SAMPLE);
    vi.spyOn(treatmentsApi, "listPatientCheckIns").mockResolvedValue({ items: [] });
    const create = vi.spyOn(treatmentsApi, "createPatientCheckIn").mockResolvedValue({
      id: "check-in-created",
      treatment_id: SAMPLE.treatment.id,
      report_type: "side_effect",
      source: "pharmacist",
      message: "Patient reports dizziness after the morning dose.",
      observed_at: null,
      created_at: "2026-05-18T10:30:00Z",
    });
    const user = userEvent.setup();

    renderAt(SAMPLE.treatment.id);

    await screen.findByText(/no patient-reported updates recorded/i);
    await user.selectOptions(screen.getByLabelText(/update type/i), "side_effect");
    await user.type(
      screen.getByLabelText(/patient-reported update/i),
      "Patient reports dizziness after the morning dose.",
    );
    await user.click(screen.getByRole("button", { name: /save clinical update/i }));

    expect(create).toHaveBeenCalledWith(SAMPLE.treatment.id, {
      report_type: "side_effect",
      source: "pharmacist",
      message: "Patient reports dizziness after the morning dose.",
      observed_at: null,
    });
    expect(
      await screen.findByText("Patient reports dizziness after the morning dose."),
    ).toBeTruthy();
    expect(screen.getByText("Source: Pharmacist")).toBeTruthy();
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
    expect(screen.getByRole("link", { name: "Clinic Hypertension Protocol" })).toHaveAttribute(
      "href",
      "/dashboard/knowledge/88888888-8888-8888-8888-888888888888",
    );
    expect(screen.getByText("Clinic asset · Relevance 91%")).toBeTruthy();
    expect(screen.getByText("Verified medical reference · Relevance 83%")).toBeTruthy();
    expect(
      screen.getByText("ACE inhibitors require monitoring for cough and dizziness."),
    ).toBeTruthy();
    expect(screen.getByText("AI Safety Review")).toBeTruthy();
    expect(screen.getByText("Requires pharmacist review")).toBeTruthy();
    expect(
      screen.getByText(/not a licensed interaction database result/i),
    ).toBeTruthy();
    expect(screen.getByText(/confidence 72%/i)).toBeTruthy();
    expect(screen.getByText("AI review suggests checking dizziness risk.")).toBeTruthy();
    expect(screen.getByText("Monitor blood pressure and dizziness.")).toBeTruthy();
    expect(screen.getByText("Ask patient to report fainting.")).toBeTruthy();
    expect(screen.getByText("Recent blood pressure readings unavailable.")).toBeTruthy();
    expect(screen.getAllByText(/Lisinopril/).length).toBeGreaterThan(1);
    expect(screen.getByText(/RxCUI 29046/)).toBeTruthy();
    expect(screen.getByText("Monitor INR closely.")).toBeTruthy();
    expect(screen.getByText("Reminder 1")).toBeTruthy();
    expect(screen.getAllByText("Lisinopril").length).toBeGreaterThan(0);
    expect(screen.getByText(/planned relative schedule with recorded adherence state/i)).toBeTruthy();
    expect(screen.getByText("Day 1, 01:00")).toBeTruthy();
    expect(screen.getByText("Planned Day 1 · +1h")).toBeTruthy();
    expect(screen.getByText("Day 1, 20:00")).toBeTruthy();
    expect(screen.getByText("Day 1, 21:00")).toBeTruthy();
  });

  it("shows latest failed attempt while rendering the last completed analysis", async () => {
    vi.spyOn(treatmentsApi, "getTreatment").mockResolvedValue(SAMPLE);
    vi.spyOn(treatmentsApi, "getAnalysis").mockResolvedValue(FAILED_WITH_LAST_COMPLETED_ANALYSIS);
    const user = userEvent.setup();

    renderAt(SAMPLE.treatment.id);

    await screen.findByText("Eleanor Vance");
    await user.click(screen.getByRole("tab", { name: /reasoning/i }));

    expect(await screen.findByText("failed")).toBeTruthy();
    expect(screen.getByText(/latest analysis attempt could not complete/i)).toBeTruthy();
    expect(screen.getByText(/analysis took too long/i)).toBeTruthy();
    expect(screen.getByRole("button", { name: /run again/i })).toBeTruthy();
    expect(
      screen.getByText("Patient should be monitored for cough and dizziness."),
    ).toBeTruthy();
  });

  it("shows adherence status beside matching schedule reminders", async () => {
    vi.spyOn(treatmentsApi, "getTreatment").mockResolvedValue(SAMPLE);
    vi.spyOn(treatmentsApi, "getAnalysis").mockResolvedValue(COMPLETED_ANALYSIS);
    vi.spyOn(treatmentsApi, "listAdherenceEvents").mockResolvedValue({
      items: SAMPLE_ADHERENCE_EVENTS,
    });
    const user = userEvent.setup();

    renderAt(SAMPLE.treatment.id);

    await screen.findByText("Eleanor Vance");
    await user.click(screen.getByRole("tab", { name: /reasoning/i }));

    expect((await screen.findAllByText("Taken")).length).toBeGreaterThan(0);
    expect(screen.getByText(/recorded by patient/i)).toBeTruthy();
  });

  it("keeps schedule usable when adherence history cannot be loaded", async () => {
    vi.spyOn(treatmentsApi, "getTreatment").mockResolvedValue(SAMPLE);
    vi.spyOn(treatmentsApi, "getAnalysis").mockResolvedValue(COMPLETED_ANALYSIS);
    vi.spyOn(treatmentsApi, "listAdherenceEvents").mockRejectedValue(new Error("unavailable"));
    const user = userEvent.setup();

    renderAt(SAMPLE.treatment.id);

    await screen.findByText("Eleanor Vance");
    await user.click(screen.getByRole("tab", { name: /reasoning/i }));

    expect(await screen.findByText("Reminder 1")).toBeTruthy();
    expect(screen.queryByText(/could not load adherence state/i)).toBeNull();
    expect(screen.getAllByText("Planned").length).toBeGreaterThan(0);
  });

  it("renders schedule adherence as read-only for the pharmacist", async () => {
    vi.spyOn(treatmentsApi, "getTreatment").mockResolvedValue(SAMPLE);
    vi.spyOn(treatmentsApi, "getAnalysis").mockResolvedValue(COMPLETED_ANALYSIS);
    vi.spyOn(treatmentsApi, "listAdherenceEvents").mockResolvedValue({ items: [] });
    const user = userEvent.setup();

    renderAt(SAMPLE.treatment.id);

    await screen.findByText("Eleanor Vance");
    await user.click(screen.getByRole("tab", { name: /reasoning/i }));
    expect(screen.queryByRole("button", { name: /mark taken/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /mark missed/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /hold dose/i })).toBeNull();
    expect(screen.getAllByText("Planned").length).toBeGreaterThan(0);
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

    await user.click(screen.getByRole("button", { name: /^run again$/i }));
    expect(screen.getByText(/replace the current analysis/i)).toBeTruthy();

    await user.click(screen.getByRole("button", { name: /confirm run again/i }));

    expect(trigger).toHaveBeenCalledWith(SAMPLE.treatment.id, { force: true });
  });

  it("does not render AI safety review when no model review was returned", async () => {
    vi.spyOn(treatmentsApi, "getTreatment").mockResolvedValue(SAMPLE);
    vi.spyOn(treatmentsApi, "getAnalysis").mockResolvedValue({
      ...COMPLETED_ANALYSIS,
      result: COMPLETED_ANALYSIS.result
        ? { ...COMPLETED_ANALYSIS.result, clinical_safety_review: null }
        : null,
    });
    const user = userEvent.setup();

    renderAt(SAMPLE.treatment.id);

    await screen.findByText("Eleanor Vance");
    await user.click(screen.getByRole("tab", { name: /reasoning/i }));

    await screen.findByText("Patient should be monitored for cough and dizziness.");
    expect(screen.queryByText("AI Safety Review")).toBeNull();
  });

  it("does not crash when older analysis results omit the AI safety review", async () => {
    vi.spyOn(treatmentsApi, "getTreatment").mockResolvedValue(SAMPLE);
    vi.spyOn(treatmentsApi, "getAnalysis").mockResolvedValue({
      ...COMPLETED_ANALYSIS,
      result: COMPLETED_ANALYSIS.result
        ? { ...COMPLETED_ANALYSIS.result, clinical_safety_review: undefined }
        : null,
    });
    const user = userEvent.setup();

    renderAt(SAMPLE.treatment.id);

    await screen.findByText("Eleanor Vance");
    await user.click(screen.getByRole("tab", { name: /reasoning/i }));

    await screen.findByText("Patient should be monitored for cough and dizziness.");
    expect(screen.queryByText("AI Safety Review")).toBeNull();
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
    expect(screen.queryByRole("button", { name: /^run again$/i })).toBeNull();
  });
});
