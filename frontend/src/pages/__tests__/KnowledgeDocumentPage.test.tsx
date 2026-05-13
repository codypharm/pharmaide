import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, NotFoundError } from "../../api/client";
import * as knowledgeApi from "../../api/knowledge";
import type { KnowledgeDocumentView } from "../../api/knowledge";
import KnowledgeDocumentPage from "../KnowledgeDocumentPage";

const DOC: KnowledgeDocumentView = {
  id: "doc-1",
  source_type: "user_upload",
  title: "Clinic Hypertension Protocol",
  mime: "application/pdf",
  status: "ready",
  chunk_count: 8,
  created_at: "2026-05-13T10:00:00Z",
  updated_at: "2026-05-13T10:05:00Z",
};

function renderPage(id = "doc-1") {
  return render(
    <MemoryRouter initialEntries={[`/dashboard/knowledge/${id}`]}>
      <Routes>
        <Route path="/dashboard/knowledge/:id" element={<KnowledgeDocumentPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("KnowledgeDocumentPage", () => {
  it("renders clinical asset metadata", async () => {
    const spy = vi.spyOn(knowledgeApi, "getKnowledgeDocument").mockResolvedValue(DOC);

    renderPage();

    await waitFor(() => expect(screen.getByText("Clinic Hypertension Protocol")).toBeTruthy());
    expect(screen.getAllByText("File ready").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/uploaded file/i).length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: /back to assets/i })).toHaveAttribute(
      "href",
      "/dashboard/knowledge",
    );
    expect(spy).toHaveBeenCalledWith("doc-1", {
      scopeId: knowledgeApi.PRE_AUTH_KB_SCOPE_ID,
    });
  });

  it("renders DailyMed references as verified material", async () => {
    vi.spyOn(knowledgeApi, "getKnowledgeDocument").mockResolvedValue({
      ...DOC,
      source_type: "dailymed",
      title: "Lisinopril Tablet",
      mime: "application/spl+xml",
    });

    renderPage();

    await waitFor(() => expect(screen.getByText("Lisinopril Tablet")).toBeTruthy());
    expect(screen.getAllByText("Verified medical reference").length).toBeGreaterThan(0);
    expect(screen.queryByText("application/spl+xml")).toBeNull();
  });

  it("renders a not found state when the clinical asset is missing", async () => {
    vi.spyOn(knowledgeApi, "getKnowledgeDocument").mockRejectedValue(
      new NotFoundError("req_missing", { detail: { error: "not_found" } }, "not_found"),
    );

    renderPage();

    await waitFor(() => expect(screen.getByText(/clinical asset not found/i)).toBeTruthy());
  });

  it("renders an unavailable state for other load failures", async () => {
    vi.spyOn(knowledgeApi, "getKnowledgeDocument").mockRejectedValue(
      new ApiError(500, "req_kb", { error: "internal_error" }, "Request failed: 500"),
    );

    renderPage();

    await waitFor(() =>
      expect(screen.getByText(/clinical asset is temporarily unavailable/i)).toBeTruthy(),
    );
    expect(screen.getByText(/req_kb/)).toBeTruthy();
  });
});
