import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { toast } from "sonner";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import NewTreatmentPage from "../NewTreatmentPage";
import { ApiError } from "../../api/client";
import * as prescriptionsApi from "../../api/prescriptions";
import { ExtractionError } from "../../api/prescriptions";
import * as treatmentsApi from "../../api/treatments";

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    warning: vi.fn(),
    error: vi.fn(),
  },
}));

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/dashboard/new-treatment"]}>
      <Routes>
        <Route path="/dashboard/new-treatment" element={<NewTreatmentPage />} />
        <Route path="/dashboard/treatments/:id" element={<div>Treatment detail</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

function renderPageWithBackStack() {
  return render(
    <MemoryRouter
      initialEntries={["/dashboard/ingestions", "/dashboard/new-treatment"]}
      initialIndex={1}
    >
      <Routes>
        <Route path="/dashboard/ingestions" element={<div>Ingestions list</div>} />
        <Route path="/dashboard/new-treatment" element={<NewTreatmentPage />} />
        <Route path="/dashboard/treatments/:id" element={<div>Treatment detail</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

async function submitValidTreatment({
  allergies = "",
  treatmentStartAt = "",
}: { allergies?: string; treatmentStartAt?: string } = {}) {
  const user = userEvent.setup();

  await user.type(screen.getByLabelText(/full name/i), "Eleanor Vance");
  await user.type(screen.getByLabelText(/date of birth/i), "1955-10-12");
  await user.type(screen.getByLabelText(/mrn number/i), "PHA-AB12CD34");
  await user.type(screen.getByLabelText(/phone number/i), "+18005551212");
  if (allergies) {
    for (const allergy of allergies.split(/[,\n]/).map((entry) => entry.trim()).filter(Boolean)) {
      await user.type(screen.getByLabelText(/allergy name/i), allergy);
      await user.click(screen.getByRole("button", { name: /add allergy/i }));
    }
  }
  await user.type(screen.getByPlaceholderText(/e.g. amoxicillin/i), "Lisinopril");
  await user.type(screen.getByPlaceholderText(/e.g. 500mg/i), "10 mg");
  await user.type(screen.getByPlaceholderText(/twice daily/i), "Once Daily (QD)");
  await user.type(screen.getByPlaceholderText(/e.g. 10 days/i), "30 days");
  if (treatmentStartAt) {
    fireEvent.change(screen.getByLabelText(/treatment starts/i), {
      target: { value: treatmentStartAt },
    });
  }
  await user.type(screen.getByLabelText(/treatment objective/i), "Monitor for cough");

  await user.click(screen.getByRole("button", { name: /review & approve/i }));
  await user.click(screen.getByRole("button", { name: /confirm & create/i }));
}

afterEach(() => {
  vi.clearAllMocks();
  vi.restoreAllMocks();
});

beforeEach(() => {
  vi.spyOn(treatmentsApi, "listTreatments").mockResolvedValue({ items: [] });
  vi.spyOn(treatmentsApi, "getAnalysis").mockResolvedValue(null);
});

describe("NewTreatmentPage", () => {
  it("lets the pharmacist open the Vision tab and choose a prescription file", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("button", { name: /vision/i }));

    expect(screen.getByText(/prescription image ingestion/i)).toBeInTheDocument();
    const input = screen.getByLabelText(/browse prescription file/i) as HTMLInputElement;
    const file = new File(["fake-pdf"], "script.pdf", { type: "application/pdf" });
    await user.upload(input, file);

    expect(input.files?.[0]).toBe(file);
    expect(screen.getByText("script.pdf")).toBeInTheDocument();
    expect(screen.getByText("Ready")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /scan & prefill form/i })).toBeInTheDocument();
  });

  it("shows drag state and attaches a dropped prescription file in the Vision tab", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("button", { name: /vision/i }));
    const dropZone = screen.getByLabelText(/drop prescription file/i);
    fireEvent.dragEnter(dropZone);

    expect(screen.getByText(/release to attach prescription/i)).toBeInTheDocument();

    const file = new File(["fake-png"], "script.png", { type: "image/png" });
    fireEvent.drop(dropZone, { dataTransfer: { files: [file] } });

    expect(screen.getByText("script.png")).toBeInTheDocument();
  });

  it("extracts an attached prescription and prefills the treatment form", async () => {
    const user = userEvent.setup();
    vi.spyOn(prescriptionsApi, "extractPrescription").mockResolvedValue({
      patient: {
        name: "Eleanor Vance",
        dob: "1955-10-12",
        mrn: "PHA-AB12CD34",
        phone: "+18005551212",
        confidence: { name: 0.91, dob: 0.87, mrn: 0.82, phone: 0.7 },
      },
      treatment: {
        clinical_objective: "Monitor for cough",
        confidence: { clinical_objective: 0.8 },
      },
      medications: [
        {
          name: "Lisinopril",
          dosage: "10 mg",
          frequency: "Once Daily (QD)",
          duration: "30 days",
          objective: null,
          confidence: {
            name: 0.95,
            dosage: 0.93,
            frequency: 0.9,
            duration: 0.88,
            objective: null,
          },
        },
      ],
      warnings: [],
    });

    renderPage();
    await user.click(screen.getByRole("button", { name: /vision/i }));
    const file = new File(["fake-pdf"], "script.pdf", { type: "application/pdf" });
    await user.upload(screen.getByLabelText(/browse prescription file/i), file);
    await user.click(screen.getByRole("button", { name: /scan & prefill form/i }));

    await waitFor(() => {
      expect(prescriptionsApi.extractPrescription).toHaveBeenCalledWith(file);
    });
    expect(screen.getByLabelText(/full name/i)).toHaveValue("Eleanor Vance");
    expect(screen.getByLabelText(/date of birth/i)).toHaveValue("1955-10-12");
    expect(screen.getByLabelText(/mrn number/i)).toHaveValue("PHA-AB12CD34");
    expect(screen.getByLabelText(/phone number/i)).toHaveValue("+18005551212");
    expect(screen.getByPlaceholderText(/e.g. amoxicillin/i)).toHaveValue("Lisinopril");
    expect(screen.getByPlaceholderText(/e.g. 500mg/i)).toHaveValue("10 mg");
    expect(screen.getByPlaceholderText(/twice daily/i)).toHaveValue("Once Daily (QD)");
    expect(screen.getByPlaceholderText(/e.g. 10 days/i)).toHaveValue("30 days");
    expect(screen.getByLabelText(/treatment objective/i)).toHaveValue("Monitor for cough");
    expect(toast.success).toHaveBeenCalledWith(
      "Prescription extracted",
      expect.objectContaining({ description: "Review the prefilled fields before submitting." }),
    );
  });

  it("shows non-blocking extraction warnings after prefill", async () => {
    const user = userEvent.setup();
    vi.spyOn(prescriptionsApi, "extractPrescription").mockResolvedValue({
      patient: {
        name: "Eleanor Vance",
        dob: null,
        mrn: null,
        phone: null,
        confidence: { name: 0.91 },
      },
      treatment: { clinical_objective: null, confidence: {} },
      medications: [
        {
          name: "Lisinopril",
          dosage: "10 mg",
          frequency: "Once Daily (QD)",
          duration: null,
          objective: null,
          confidence: { name: 0.95, dosage: 0.93, frequency: 0.9 },
        },
      ],
      warnings: ["Duration was not visible on the uploaded prescription."],
    });

    renderPage();
    await user.click(screen.getByRole("button", { name: /vision/i }));
    await user.upload(
      screen.getByLabelText(/browse prescription file/i),
      new File(["fake-png"], "script.png", { type: "image/png" }),
    );
    await user.click(screen.getByRole("button", { name: /scan & prefill form/i }));

    expect(await screen.findByText(/extraction warnings/i)).toBeInTheDocument();
    expect(screen.getByText("Duration was not visible on the uploaded prescription.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /review & approve/i })).toBeEnabled();
  });

  it("marks extracted fields and clears the marker when the pharmacist edits them", async () => {
    const user = userEvent.setup();
    vi.spyOn(prescriptionsApi, "extractPrescription").mockResolvedValue({
      patient: {
        name: "Eleanor Vance",
        dob: null,
        mrn: null,
        phone: null,
        confidence: { name: 0.91 },
      },
      treatment: { clinical_objective: null, confidence: {} },
      medications: [
        {
          name: "Lisinopril",
          dosage: "10 mg",
          frequency: null,
          duration: null,
          objective: null,
          confidence: { name: 0.95, dosage: 0.93 },
        },
      ],
      warnings: [],
    });

    renderPage();
    await user.click(screen.getByRole("button", { name: /vision/i }));
    await user.upload(
      screen.getByLabelText(/browse prescription file/i),
      new File(["fake-png"], "script.png", { type: "image/png" }),
    );
    await user.click(screen.getByRole("button", { name: /scan & prefill form/i }));

    const name = await screen.findByLabelText(/full name/i);
    const medication = screen.getByPlaceholderText(/e.g. amoxicillin/i);
    expect(name).toHaveAttribute("data-extraction-origin", "vision");
    expect(medication).toHaveAttribute("data-extraction-origin", "vision");

    await user.clear(name);
    await user.type(name, "Eleanor V.");

    expect(name).not.toHaveAttribute("data-extraction-origin");
    expect(medication).toHaveAttribute("data-extraction-origin", "vision");
  });

  it("marks low-confidence extracted fields and clears that marker when edited", async () => {
    const user = userEvent.setup();
    vi.spyOn(prescriptionsApi, "extractPrescription").mockResolvedValue({
      patient: {
        name: "Eleanor Vance",
        dob: null,
        mrn: null,
        phone: "+18005551212",
        confidence: { name: 0.91, phone: 0.62 },
      },
      treatment: { clinical_objective: null, confidence: {} },
      medications: [
        {
          name: "Lisinopril",
          dosage: "10 mg",
          frequency: "Once Daily (QD)",
          duration: null,
          objective: null,
          confidence: { name: 0.95, dosage: 0.93, frequency: 0.58 },
        },
      ],
      warnings: [],
    });

    renderPage();
    await user.click(screen.getByRole("button", { name: /vision/i }));
    await user.upload(
      screen.getByLabelText(/browse prescription file/i),
      new File(["fake-png"], "script.png", { type: "image/png" }),
    );
    await user.click(screen.getByRole("button", { name: /scan & prefill form/i }));

    const phone = await screen.findByLabelText(/phone number/i);
    const frequency = screen.getByPlaceholderText(/twice daily/i);
    expect(phone).toHaveAttribute("data-extraction-confidence", "low");
    expect(phone).toHaveAttribute("title", "AI confidence low - verify");
    expect(frequency).toHaveAttribute("data-extraction-confidence", "low");

    await user.clear(phone);
    await user.type(phone, "+18005550000");

    expect(phone).not.toHaveAttribute("data-extraction-confidence");
    expect(frequency).toHaveAttribute("data-extraction-confidence", "low");
  });

  it("shows extraction failure with request id and lets pharmacist use form entry", async () => {
    const user = userEvent.setup();
    vi.spyOn(prescriptionsApi, "extractPrescription").mockRejectedValue(
      new ExtractionError(
        new ApiError(
          422,
          "req_extract_123",
          { detail: { error: "pdf_render_failed" } },
          "Request failed: 422",
        ),
        "pdf_render_failed",
      ),
    );

    renderPage();
    await user.click(screen.getByRole("button", { name: /vision/i }));
    await user.upload(
      screen.getByLabelText(/browse prescription file/i),
      new File(["fake-pdf"], "script.pdf", { type: "application/pdf" }),
    );
    await user.click(screen.getByRole("button", { name: /scan & prefill form/i }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("This PDF could not be read");
    expect(alert).toHaveTextContent("req_extract_123");

    await user.click(screen.getByRole("button", { name: /use form entry/i }));

    expect(screen.getByText(/manual regimen entry/i)).toBeInTheDocument();
  });

  it("parses pasted manual treatment text into the reviewed form", async () => {
    const user = userEvent.setup();
    const create = vi.spyOn(treatmentsApi, "createTreatment").mockResolvedValue({
      treatment_id: "treatment-1",
      patient_id: "patient-1",
      analysis_id: "analysis-1",
    });

    renderPage();
    await user.click(screen.getByRole("button", { name: /^manual$/i }));
    await user.type(
      screen.getByLabelText(/pasted prescription text/i),
      "Amoxicillin 500mg twice daily for 7 days\nMetronidazole 400mg three times daily for 5 days",
    );
    await user.click(screen.getByRole("button", { name: /extract clinical entities/i }));

    expect(screen.getByText(/manual regimen entry/i)).toBeInTheDocument();
    expect(screen.getAllByPlaceholderText(/e.g. amoxicillin/i)[0]).toHaveValue("Amoxicillin");
    expect(screen.getAllByPlaceholderText(/e.g. 500mg/i)[0]).toHaveValue("500mg");
    expect(screen.getAllByPlaceholderText(/twice daily/i)[0]).toHaveValue("twice daily");
    expect(screen.getAllByPlaceholderText(/e.g. 10 days/i)[0]).toHaveValue("7 days");
    expect(screen.getByDisplayValue("Metronidazole")).toBeInTheDocument();

    await user.type(screen.getByLabelText(/full name/i), "Eleanor Vance");
    await user.type(screen.getByLabelText(/date of birth/i), "1955-10-12");
    await user.type(screen.getByLabelText(/mrn number/i), "PHA-AB12CD34");
    await user.type(screen.getByLabelText(/phone number/i), "+18005551212");
    await user.type(screen.getByLabelText(/treatment objective/i), "Monitor improvement");
    await user.click(screen.getByRole("button", { name: /review & approve/i }));
    await user.click(screen.getByRole("button", { name: /confirm & create/i }));

    await waitFor(() => {
      expect(create).toHaveBeenCalledWith(
        expect.objectContaining({
          ingestion_method: "manual",
          medications: [
            expect.objectContaining({ name: "Amoxicillin", dosage: "500mg" }),
            expect.objectContaining({ name: "Metronidazole", dosage: "400mg" }),
          ],
        }),
      );
    });
  });

  it("clears the current draft without navigating away", async () => {
    const user = userEvent.setup();
    renderPageWithBackStack();

    await user.type(screen.getByLabelText(/full name/i), "Eleanor Vance");
    await user.type(screen.getByPlaceholderText(/e.g. amoxicillin/i), "Lisinopril");
    await user.click(screen.getByRole("button", { name: /clear form/i }));

    expect(screen.queryByText("Ingestions list")).not.toBeInTheDocument();
    expect(screen.getByLabelText(/full name/i)).toHaveValue("");
    expect(screen.getByPlaceholderText(/e.g. amoxicillin/i)).toHaveValue("");
  });

  it("shows the server-created analysis id after creating a treatment", async () => {
    vi.spyOn(treatmentsApi, "createTreatment").mockResolvedValue({
      treatment_id: "treatment-1",
      patient_id: "patient-1",
      analysis_id: "analysis-1",
    });
    const trigger = vi.spyOn(treatmentsApi, "triggerAnalysis");

    renderPage();
    await submitValidTreatment();

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith(
        "Treatment created",
        expect.objectContaining({
          description: expect.stringContaining("Analysis ID: analysis"),
        }),
      );
    });
    expect(trigger).not.toHaveBeenCalled();
  });

  it("adds and removes known allergy chips", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.type(screen.getByLabelText(/allergy name/i), "Penicillin");
    await user.click(screen.getByRole("button", { name: /add allergy/i }));

    expect(screen.getByText("Penicillin")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /remove penicillin/i }));

    expect(screen.queryByText("Penicillin")).not.toBeInTheDocument();
  });

  it("submits known allergy chips with the treatment payload", async () => {
    const create = vi.spyOn(treatmentsApi, "createTreatment").mockResolvedValue({
      treatment_id: "treatment-1",
      patient_id: "patient-1",
      analysis_id: "analysis-1",
    });

    renderPage();
    await submitValidTreatment({ allergies: " Penicillin\nSulfa, latex " });

    await waitFor(() => {
      expect(create).toHaveBeenCalledWith(
        expect.objectContaining({
          patient: expect.objectContaining({
            allergies: ["Penicillin", "Sulfa", "latex"],
          }),
        }),
      );
    });
  });

  it("submits the treatment start as a timezone-aware timestamp", async () => {
    const create = vi.spyOn(treatmentsApi, "createTreatment").mockResolvedValue({
      treatment_id: "treatment-1",
      patient_id: "patient-1",
      analysis_id: "analysis-1",
    });
    const localStart = "2026-05-16T09:30";

    renderPage();
    await submitValidTreatment({ treatmentStartAt: localStart });

    await waitFor(() => {
      expect(create).toHaveBeenCalledWith(
        expect.objectContaining({
          treatment: expect.objectContaining({
            treatment_start_at: new Date(localStart).toISOString(),
          }),
        }),
      );
    });
  });

  it("handles missing analysis id as pending backend startup", async () => {
    vi.spyOn(treatmentsApi, "createTreatment").mockResolvedValue({
      treatment_id: "treatment-1",
      patient_id: "patient-1",
      analysis_id: null,
    });

    renderPage();
    await submitValidTreatment();

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith(
        "Treatment created",
        expect.objectContaining({
          action: expect.objectContaining({ label: "View" }),
          description: expect.stringContaining("Analysis pending"),
        }),
      );
    });
  });

  it("shows pending treatments and starts cycles once analysis is completed", async () => {
    const user = userEvent.setup();
    vi.spyOn(treatmentsApi, "listTreatments").mockResolvedValue({
      items: [
        treatmentListItem("pending-running", "Eleanor Vance", "Lisinopril", "pending"),
        treatmentListItem("pending-ready", "Marcus Chen", "Metformin", "pending"),
        treatmentListItem("active-treatment", "Ava Patel", "Amoxicillin", "active"),
      ],
    });
    vi.spyOn(treatmentsApi, "getAnalysis").mockImplementation(async (treatmentId) => {
      if (treatmentId === "pending-ready") {
        return {
          id: "analysis-ready",
          treatment_id: treatmentId,
          status: "completed",
          result: {
            groundings: [],
            ddi_warnings: [],
            schedule: null,
            kb_citations: [],
            clinical_safety_review: null,
            reasoning: null,
            degraded: false,
            partial_results: false,
            completed_stages: [],
          },
          error_text: null,
          started_at: "2026-05-16T10:00:00Z",
          completed_at: "2026-05-16T10:01:00Z",
          created_at: "2026-05-16T10:00:00Z",
        } as treatmentsApi.TreatmentAnalysisRow;
      }
      return {
        id: "analysis-running",
        treatment_id: treatmentId,
        status: "running",
        result: null,
        error_text: null,
        started_at: "2026-05-16T10:00:00Z",
        completed_at: null,
        created_at: "2026-05-16T10:00:00Z",
      } as treatmentsApi.TreatmentAnalysisRow;
    });
    const startCycle = vi.spyOn(treatmentsApi, "startTreatmentCycle").mockResolvedValue({
      id: "pending-ready",
      patient_id: "patient-pending-ready",
      status: "active",
      chat_response_mode: "ai_active",
      automation_mode: "active",
      clinical_objective: null,
      treatment_start_at: null,
      created_at: "2026-05-16T10:00:00Z",
    });

    renderPage();
    await user.click(screen.getByRole("tab", { name: /pending handoffs/i }));

    expect(await screen.findByText("Eleanor Vance")).toBeInTheDocument();
    expect(screen.getByText("Analyzing")).toBeInTheDocument();
    expect(screen.getByText("Marcus Chen")).toBeInTheDocument();
    expect(screen.getByText("Ready to start")).toBeInTheDocument();
    expect(screen.queryByText("Ava Patel")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /start cycle for marcus chen/i }));

    expect(startCycle).toHaveBeenCalledWith("pending-ready");
    await waitFor(() => expect(screen.queryByText("Marcus Chen")).not.toBeInTheDocument());
    expect(toast.success).toHaveBeenCalledWith("Treatment cycle active", {
      description: "Monitoring has started for Marcus Chen.",
    });
  });
});

function treatmentListItem(
  id: string,
  patientName: string,
  medicationName: string,
  status: string,
): treatmentsApi.TreatmentListItem {
  return {
    patient: {
      id: `patient-${id}`,
      name: patientName,
      dob: "1955-10-12",
      mrn: `MRN-${id}`,
      phone: "+18005551212",
      allergies: [],
    },
    treatment: {
      id,
      patient_id: `patient-${id}`,
      status,
      chat_response_mode: "ai_active",
      automation_mode: "active",
      clinical_objective: null,
      treatment_start_at: null,
      created_at: "2026-05-16T10:00:00Z",
    },
    medication_count: 1,
    first_medication_name: medicationName,
  };
}
