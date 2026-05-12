import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { toast } from "sonner";
import { afterEach, describe, expect, it, vi } from "vitest";

import NewTreatmentPage from "../NewTreatmentPage";
import { ConflictError } from "../../api/client";
import * as prescriptionsApi from "../../api/prescriptions";
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

async function submitValidTreatment() {
  const user = userEvent.setup();

  await user.type(screen.getByLabelText(/full name/i), "Eleanor Vance");
  await user.type(screen.getByLabelText(/date of birth/i), "1955-10-12");
  await user.type(screen.getByLabelText(/mrn number/i), "PHA-AB12CD34");
  await user.type(screen.getByLabelText(/phone number/i), "+18005551212");
  await user.type(screen.getByPlaceholderText(/e.g. amoxicillin/i), "Lisinopril");
  await user.type(screen.getByPlaceholderText(/e.g. 500mg/i), "10 mg");
  await user.type(screen.getByPlaceholderText(/twice daily/i), "Once Daily (QD)");
  await user.type(screen.getByPlaceholderText(/e.g. 10 days/i), "30 days");
  await user.type(screen.getByLabelText(/treatment objective/i), "Monitor for cough");

  await user.click(screen.getByRole("button", { name: /review & approve/i }));
  await user.click(screen.getByRole("button", { name: /confirm & create/i }));
}

afterEach(() => {
  vi.clearAllMocks();
  vi.restoreAllMocks();
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
    await user.click(screen.getByRole("button", { name: /extract prescription/i }));

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

  it("starts the first analysis automatically after creating a treatment", async () => {
    vi.spyOn(treatmentsApi, "createTreatment").mockResolvedValue({
      treatment_id: "treatment-1",
      patient_id: "patient-1",
    });
    const trigger = vi
      .spyOn(treatmentsApi, "triggerAnalysis")
      .mockResolvedValue({ analysis_id: "analysis-1" });

    renderPage();
    await submitValidTreatment();

    await waitFor(() => {
      expect(trigger).toHaveBeenCalledWith("treatment-1");
    });
  });

  it("does not treat duplicate active analysis as a create failure", async () => {
    vi.spyOn(treatmentsApi, "createTreatment").mockResolvedValue({
      treatment_id: "treatment-1",
      patient_id: "patient-1",
    });
    vi.spyOn(treatmentsApi, "triggerAnalysis").mockRejectedValue(
      new ConflictError(
        "req_conflict",
        { detail: { error: "analysis_in_progress" } },
        "analysis_in_progress",
      ),
    );

    renderPage();
    await submitValidTreatment();

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith(
        "Treatment created",
        expect.objectContaining({
          action: expect.objectContaining({ label: "View" }),
        }),
      );
    });
    expect(toast.warning).not.toHaveBeenCalled();
  });
});
