import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import IngestionsPage from "../IngestionsPage";
import { ApiError } from "../../api/client";
import * as treatmentsApi from "../../api/treatments";
import type { TreatmentList, TreatmentListItem } from "../../api/treatments";

function row(suffix: string): TreatmentListItem {
  return {
    patient: {
      id: `p-${suffix}`,
      name: `Patient ${suffix}`,
      dob: "1955-10-12",
      mrn: `MRN-${suffix}`,
      phone: "+18005551212",
      allergies: [],
    },
    treatment: {
      id: `t-${suffix}`,
      patient_id: `p-${suffix}`,
      status: "pending",
      chat_response_mode: "ai_active",
      automation_mode: "active",
      clinical_objective: null,
      treatment_start_at: null,
      created_at: "2026-05-11T12:00:00Z",
    },
    medication_count: 1,
    first_medication_name: "Lisinopril",
  };
}

function renderPage({ isPrivacyMode = false }: { isPrivacyMode?: boolean } = {}) {
  // The page reads isPrivacyMode via useOutletContext, so it must be
  // rendered as a nested route under a parent that supplies the context.
  return render(
    <MemoryRouter initialEntries={["/dashboard/ingestions"]}>
      <Routes>
        <Route element={<Outlet context={{ isPrivacyMode }} />}>
          <Route path="/dashboard/ingestions" element={<IngestionsPage />} />
        </Route>
        <Route path="/dashboard/treatments/:id" element={<div>detail</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("IngestionsPage", () => {
  it("renders rows from listTreatments", async () => {
    vi.spyOn(treatmentsApi, "listTreatments").mockResolvedValue({
      items: [row("001"), row("002")],
    } satisfies TreatmentList);

    renderPage();

    await waitFor(() => expect(screen.getByText("Patient 001")).toBeTruthy());
    expect(screen.getByText("Patient 002")).toBeTruthy();
    expect(screen.getAllByText("MRN-001").length).toBeGreaterThan(0);
  });

  it("shows an empty state when there are no ingestions", async () => {
    vi.spyOn(treatmentsApi, "listTreatments").mockResolvedValue({ items: [] });

    renderPage();

    await waitFor(() => expect(screen.getByText(/no data available/i)).toBeTruthy());
    expect(screen.getByText(/no treatments registered/i)).toBeTruthy();
    expect(screen.getAllByRole("link", { name: /new treatment/i }).length).toBeGreaterThan(0);
  });

  it("shows an error state on API failure", async () => {
    vi.spyOn(treatmentsApi, "listTreatments").mockRejectedValue(
      new ApiError(500, "req_x", { error: "internal_error" }, "Request failed: 500"),
    );

    renderPage();

    await waitFor(() => expect(screen.getByText(/could not load/i)).toBeTruthy());
    expect(screen.getByText(/req_x/)).toBeTruthy();
  });

  it("appends a second page when Load more is clicked", async () => {
    const spy = vi
      .spyOn(treatmentsApi, "listTreatments")
      .mockResolvedValueOnce({ items: Array.from({ length: 50 }, (_, i) => row(`a${i}`)) })
      .mockResolvedValueOnce({ items: [row("b1"), row("b2")] });

    const user = userEvent.setup();
    renderPage();

    await waitFor(() => expect(screen.getByText("Patient a0")).toBeTruthy());
    expect(spy).toHaveBeenCalledWith({ limit: 50, offset: 0 });

    await user.click(screen.getByRole("button", { name: /load more/i }));

    await waitFor(() => expect(screen.getByText("Patient b1")).toBeTruthy());
    expect(spy).toHaveBeenCalledWith({ limit: 50, offset: 50 });
    // First-page row still present — second page is appended, not replaced.
    expect(screen.getByText("Patient a0")).toBeTruthy();
  });

  it("blurs patient name and MRN when privacy mode is on", async () => {
    vi.spyOn(treatmentsApi, "listTreatments").mockResolvedValue({ items: [row("001")] });

    renderPage({ isPrivacyMode: true });

    const name = await screen.findByText("Patient 001");
    const mrn = screen.getByText("MRN-001");
    expect(name.className).toMatch(/blur-sm/);
    expect(mrn.className).toMatch(/blur-sm/);
  });

  it("hides Load more when the last page returned fewer than 50 rows", async () => {
    vi.spyOn(treatmentsApi, "listTreatments").mockResolvedValue({
      items: [row("only")],
    });

    renderPage();

    await waitFor(() => expect(screen.getByText("Patient only")).toBeTruthy());
    expect(screen.queryByRole("button", { name: /load more/i })).not.toBeInTheDocument();
  });
});
