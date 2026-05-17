import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as auditsApi from "../../api/audits";
import type { AuditLogEntryList } from "../../api/audits";
import { ApiError } from "../../api/client";
import SystemAuditsPage from "../SystemAuditsPage";

const AUDITS: AuditLogEntryList = {
  items: [
    {
      id: "11111111-1111-4111-8111-111111111111",
      actor_id: null,
      event_type: "analysis_started",
      resource_type: "treatment",
      resource_id: "22222222-2222-4222-8222-222222222222",
      payload: { medication_count: 2 },
      created_at: "2026-05-15T10:00:00Z",
    },
    {
      id: "33333333-3333-4333-8333-333333333333",
      actor_id: "44444444-4444-4444-8444-444444444444",
      event_type: "triage_item_status_changed",
      resource_type: "triage_item",
      resource_id: "55555555-5555-4555-8555-555555555555",
      payload: { old_status: "open", new_status: "acknowledged" },
      created_at: "2026-05-15T11:00:00Z",
    },
  ],
};

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/dashboard/audits"]}>
      <Routes>
        <Route element={<Outlet context={{ isPrivacyMode: false }} />}>
          <Route path="/dashboard/audits" element={<SystemAuditsPage />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("SystemAuditsPage", () => {
  it("renders real audit log entries from the audit API", async () => {
    const spy = vi.spyOn(auditsApi, "listAuditLogEntries").mockResolvedValue(AUDITS);

    renderPage();

    await screen.findByText("Analysis Started");
    expect(screen.getByText("Triage Item Status Changed")).toBeTruthy();
    expect(screen.getAllByText("Agent").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Human").length).toBeGreaterThan(0);
    expect(screen.getByText(/medication_count: 2/i)).toBeTruthy();
    expect(spy).toHaveBeenCalledWith({ limit: 50, offset: 0 });
  });

  it("filters loaded audits by event or resource text", async () => {
    const user = userEvent.setup();
    vi.spyOn(auditsApi, "listAuditLogEntries").mockResolvedValue(AUDITS);

    renderPage();

    await screen.findByText("Analysis Started");
    await user.type(screen.getByPlaceholderText(/search audits/i), "triage");

    expect(screen.getByText("Triage Item Status Changed")).toBeTruthy();
    expect(screen.queryByText("Analysis Started")).toBeNull();
  });

  it("filters loaded audits with the inline actor switch", async () => {
    const user = userEvent.setup();
    vi.spyOn(auditsApi, "listAuditLogEntries").mockResolvedValue(AUDITS);

    renderPage();

    await screen.findByText("Analysis Started");
    await user.click(screen.getByRole("button", { name: /^human$/i }));

    expect(screen.getByText("Triage Item Status Changed")).toBeTruthy();
    expect(screen.queryByText("Analysis Started")).toBeNull();
  });

  it("requests backend-filtered audits from pharmacist-friendly filter labels", async () => {
    const user = userEvent.setup();
    const spy = vi.spyOn(auditsApi, "listAuditLogEntries").mockResolvedValue(AUDITS);

    renderPage();

    await screen.findByText("Analysis Started");
    await user.selectOptions(screen.getByLabelText(/event type/i), "triage_item_status_changed");
    await user.selectOptions(screen.getByLabelText(/resource type/i), "triage_item");
    await user.type(screen.getByLabelText(/actor id/i), "44444444-4444-4444-8444-444444444444");
    await user.click(screen.getByRole("button", { name: /apply audit filters/i }));

    await waitFor(() =>
      expect(spy).toHaveBeenLastCalledWith({
        limit: 50,
        offset: 0,
        event_type: "triage_item_status_changed",
        resource_type: "triage_item",
        actor_id: "44444444-4444-4444-8444-444444444444",
      }),
    );
  });

  it("exports backend-filtered audit CSV from applied exact filters", async () => {
    const user = userEvent.setup();
    vi.spyOn(auditsApi, "listAuditLogEntries").mockResolvedValue(AUDITS);
    const exportSpy = vi
      .spyOn(auditsApi, "exportAuditLogEntries")
      .mockResolvedValue("id,event_type\n33333333-3333-4333-8333-333333333333,triage_item_status_changed\n");
    const createObjectUrl = vi
      .spyOn(URL, "createObjectURL")
      .mockReturnValue("blob:audit-export");
    const revokeObjectUrl = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => undefined);

    renderPage();

    await screen.findByText("Analysis Started");
    await user.selectOptions(screen.getByLabelText(/event type/i), "triage_item_status_changed");
    await user.selectOptions(screen.getByLabelText(/resource type/i), "triage_item");
    await user.type(screen.getByLabelText(/actor id/i), "44444444-4444-4444-8444-444444444444");
    await user.click(screen.getByRole("button", { name: /apply audit filters/i }));
    await user.click(screen.getByRole("button", { name: /export audit trail/i }));

    await waitFor(() =>
      expect(exportSpy).toHaveBeenCalledWith({
        limit: 1000,
        event_type: "triage_item_status_changed",
        resource_type: "triage_item",
        actor_id: "44444444-4444-4444-8444-444444444444",
      }),
    );
    expect(createObjectUrl).toHaveBeenCalled();
    expect(click).toHaveBeenCalled();
    expect(revokeObjectUrl).toHaveBeenCalledWith("blob:audit-export");
  });

  it("shows an empty state when no audit entries exist yet", async () => {
    vi.spyOn(auditsApi, "listAuditLogEntries").mockResolvedValue({ items: [] });

    renderPage();

    await screen.findByText(/no audit events recorded yet/i);
  });

  it("shows a retryable error state when audits cannot be loaded", async () => {
    vi.spyOn(auditsApi, "listAuditLogEntries").mockRejectedValue(
      new ApiError(500, "req_audit", { error: "internal_error" }, "Request failed: 500"),
    );

    renderPage();

    await screen.findByText(/audit trail is temporarily unavailable/i);
    expect(screen.getByText(/req_audit/i)).toBeTruthy();
  });
});
