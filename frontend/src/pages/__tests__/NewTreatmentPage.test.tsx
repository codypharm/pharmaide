import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { toast } from "sonner";
import { afterEach, describe, expect, it, vi } from "vitest";

import NewTreatmentPage from "../NewTreatmentPage";
import { ConflictError } from "../../api/client";
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
