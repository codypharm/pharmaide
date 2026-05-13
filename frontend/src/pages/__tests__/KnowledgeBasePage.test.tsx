import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, NotFoundError } from "../../api/client";
import * as knowledgeApi from "../../api/knowledge";
import type { KnowledgeDocumentList, KnowledgeDocumentView } from "../../api/knowledge";
import KnowledgeBasePage from "../KnowledgeBasePage";

const DOC: KnowledgeDocumentView = {
  id: "doc-1",
  title: "Anticoagulation Protocol",
  mime: "application/pdf",
  status: "ready",
  chunk_count: 8,
  created_at: "2026-05-13T10:00:00Z",
  updated_at: "2026-05-13T10:05:00Z",
};

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/dashboard/knowledge"]}>
      <Routes>
        <Route element={<Outlet context={{ isPrivacyMode: false }} />}>
          <Route path="/dashboard/knowledge" element={<KnowledgeBasePage />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("KnowledgeBasePage", () => {
  it("renders documents from the knowledge API", async () => {
    const spy = vi.spyOn(knowledgeApi, "listKnowledgeDocuments").mockResolvedValue({
      items: [DOC],
    } satisfies KnowledgeDocumentList);

    renderPage();

    await waitFor(() => expect(screen.getByText("Anticoagulation Protocol")).toBeTruthy());
    expect(screen.getAllByText("Ready").length).toBeGreaterThan(0);
    expect(screen.getByText("8 chunks")).toBeTruthy();
    expect(spy).toHaveBeenCalledWith({
      scopeId: knowledgeApi.PRE_AUTH_KB_SCOPE_ID,
      limit: 50,
      offset: 0,
    });
  });

  it("shows an empty state when no documents have been uploaded", async () => {
    vi.spyOn(knowledgeApi, "listKnowledgeDocuments").mockResolvedValue({ items: [] });

    renderPage();

    await waitFor(() => expect(screen.getByText(/no clinical assets uploaded/i)).toBeTruthy());
    expect(screen.queryByText(/retrievable chunks/i)).toBeNull();
  });

  it("shows an error state when documents cannot be loaded", async () => {
    vi.spyOn(knowledgeApi, "listKnowledgeDocuments").mockRejectedValue(
      new ApiError(500, "req_kb", { error: "internal_error" }, "Request failed: 500"),
    );

    renderPage();

    await waitFor(() => expect(screen.getByText(/clinical assets are temporarily unavailable/i)).toBeTruthy());
    expect(screen.getByText(/req_kb/)).toBeTruthy();
  });

  it("shows a pharmacist-safe preparation message when the route is unavailable", async () => {
    vi.spyOn(knowledgeApi, "listKnowledgeDocuments").mockRejectedValue(
      new NotFoundError("req_missing", { detail: { error: "not_found" } }, "not_found"),
    );

    renderPage();

    await waitFor(() => expect(screen.getByText(/clinical assets are being prepared/i)).toBeTruthy());
    expect(screen.getByText(/continue reviewing treatments/i)).toBeTruthy();
  });

  it("shows a pharmacist-safe unavailable message when the request fails before an API response", async () => {
    vi.spyOn(knowledgeApi, "listKnowledgeDocuments").mockRejectedValue(
      new TypeError("Failed to fetch"),
    );

    renderPage();

    await waitFor(() => expect(screen.getByText(/clinical assets are temporarily unavailable/i)).toBeTruthy());
    expect(screen.getByText(/continue without uploaded reference material/i)).toBeTruthy();
  });

  it("uploads a selected document and refreshes the list", async () => {
    const user = userEvent.setup();
    vi.spyOn(knowledgeApi, "listKnowledgeDocuments")
      .mockResolvedValueOnce({ items: [] })
      .mockResolvedValueOnce({ items: [DOC] });
    const uploadSpy = vi
      .spyOn(knowledgeApi, "uploadKnowledgeDocument")
      .mockResolvedValue({ document_id: "doc-1", status: "ingesting" });

    renderPage();
    await screen.findByText(/no clinical assets uploaded/i);

    const file = new File(["protocol"], "protocol.pdf", { type: "application/pdf" });
    await user.upload(screen.getByLabelText(/upload clinical asset/i), file);

    await waitFor(() => expect(uploadSpy).toHaveBeenCalledWith(file, {
      scopeId: knowledgeApi.PRE_AUTH_KB_SCOPE_ID,
    }));
    await waitFor(() => expect(screen.getByText("Anticoagulation Protocol")).toBeTruthy());
  });

  it("soft-deletes a document after confirmation", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.spyOn(knowledgeApi, "listKnowledgeDocuments")
      .mockResolvedValueOnce({ items: [DOC] })
      .mockResolvedValueOnce({ items: [] });
    const deleteSpy = vi.spyOn(knowledgeApi, "deleteKnowledgeDocument").mockResolvedValue();

    renderPage();
    await screen.findByText("Anticoagulation Protocol");

    await user.click(screen.getByRole("button", { name: /delete anticoagulation protocol/i }));

    await waitFor(() => expect(deleteSpy).toHaveBeenCalledWith("doc-1", {
      scopeId: knowledgeApi.PRE_AUTH_KB_SCOPE_ID,
    }));
    await waitFor(() => expect(screen.getByText(/no clinical assets uploaded/i)).toBeTruthy());
  });
});
