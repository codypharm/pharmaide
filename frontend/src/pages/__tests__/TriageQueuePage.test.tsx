import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as triageApi from "../../api/triage";
import type { TriageItemList, TriageItemView } from "../../api/triage";
import TriageQueuePage from "../TriageQueuePage";

const OPEN_ITEM: TriageItemView = {
  id: "triage-1",
  treatment_id: "22222222-2222-2222-2222-222222222222",
  conversation_message_id: "33333333-3333-3333-3333-333333333333",
  reason: "referee",
  status: "open",
  created_at: "2026-05-15T10:00:00Z",
};

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/dashboard/triage"]}>
      <Routes>
        <Route element={<Outlet context={{ isPrivacyMode: false }} />}>
          <Route path="/dashboard/triage" element={<TriageQueuePage />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("TriageQueuePage", () => {
  it("loads real triage items and moves an item through review states", async () => {
    const user = userEvent.setup();
    vi.spyOn(triageApi, "listTriageItems").mockResolvedValue({
      items: [OPEN_ITEM],
    } satisfies TriageItemList);
    const updateSpy = vi
      .spyOn(triageApi, "updateTriageItemStatus")
      .mockResolvedValueOnce({ ...OPEN_ITEM, status: "acknowledged" })
      .mockResolvedValueOnce({ ...OPEN_ITEM, status: "resolved" });

    renderPage();

    await screen.findByText("Clinical draft review");
    expect(screen.getByText("22222222")).toBeTruthy();
    expect(screen.getAllByText("Open").length).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: /acknowledge review item/i }));
    await waitFor(() => expect(updateSpy).toHaveBeenCalledWith("triage-1", "acknowledged"));
    expect(screen.getAllByText("Acknowledged").length).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: /resolve review item/i }));
    await waitFor(() => expect(updateSpy).toHaveBeenCalledWith("triage-1", "resolved"));
    expect(screen.getAllByText("Resolved").length).toBeGreaterThan(0);
  });

  it("shows a calm empty state when no patients need review", async () => {
    vi.spyOn(triageApi, "listTriageItems").mockResolvedValue({ items: [] });

    renderPage();

    await screen.findByText(/no patients need review right now/i);
    expect(screen.queryByText(/could not load/i)).toBeNull();
  });
});
