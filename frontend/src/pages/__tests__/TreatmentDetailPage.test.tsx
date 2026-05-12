import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import TreatmentDetailPage from "../TreatmentDetailPage";
import { ApiError, NotFoundError } from "../../api/client";
import * as treatmentsApi from "../../api/treatments";
import type { TreatmentDetail } from "../../api/treatments";

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
});
