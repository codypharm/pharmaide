import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as treatmentsApi from "../../api/treatments";
import type { ConversationMessageList } from "../../api/treatments";
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

const CONVERSATION_MESSAGES: ConversationMessageList = {
  items: [
    {
      id: "44444444-4444-4444-4444-444444444444",
      treatment_id: OPEN_ITEM.treatment_id,
      direction: "inbound",
      sender_type: "patient",
      channel: "whatsapp",
      status: "received",
      body: "I feel dizzy after the second dose.",
      safety_hold_reason: null,
      external_message_id: null,
      created_at: "2026-05-15T10:01:00Z",
    },
    {
      id: OPEN_ITEM.conversation_message_id!,
      treatment_id: OPEN_ITEM.treatment_id,
      direction: "outbound",
      sender_type: "assistant",
      channel: "whatsapp",
      status: "held_for_review",
      body: "You can skip the next dose.",
      safety_hold_reason: "referee",
      external_message_id: null,
      created_at: "2026-05-15T10:02:00Z",
    },
  ],
};

function renderPage({ isPrivacyMode = false }: { isPrivacyMode?: boolean } = {}) {
  return render(
    <MemoryRouter initialEntries={["/dashboard/triage"]}>
      <Routes>
        <Route element={<Outlet context={{ isPrivacyMode }} />}>
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
    vi.spyOn(treatmentsApi, "listConversationMessages").mockResolvedValue(CONVERSATION_MESSAGES);
    const updateSpy = vi
      .spyOn(triageApi, "updateTriageItemStatus")
      .mockResolvedValueOnce({ ...OPEN_ITEM, status: "acknowledged" });
    const approveSpy = vi.spyOn(triageApi, "approveTriageItem").mockResolvedValue({
      triage_item: { ...OPEN_ITEM, status: "resolved" },
      approved_message: {
        ...CONVERSATION_MESSAGES.items[1],
        status: "approved",
      },
    });
    const queueDeliverySpy = vi.spyOn(triageApi, "queueTriageItemDelivery").mockResolvedValue({
      triage_item: { ...OPEN_ITEM, status: "resolved" },
      queued_message: {
        ...CONVERSATION_MESSAGES.items[1],
        status: "queued",
      },
    });

    renderPage();

    await screen.findByText("Clinical draft review");
    expect(screen.getByText("22222222")).toBeTruthy();
    expect(screen.getAllByText("Open").length).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: /review item/i }));
    await user.click(screen.getByRole("button", { name: /start review item/i }));
    await waitFor(() => expect(updateSpy).toHaveBeenCalledWith("triage-1", "acknowledged"));
    expect(screen.getAllByText("Acknowledged").length).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: /approve draft item/i }));
    await waitFor(() => expect(approveSpy).toHaveBeenCalledWith("triage-1"));
    expect(screen.getAllByText("Resolved").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Approved, not sent").length).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: /queue delivery item/i }));
    await waitFor(() =>
      expect(queueDeliverySpy).toHaveBeenCalledWith("triage-1"),
    );
    expect(screen.getAllByText("Queued for delivery").length).toBeGreaterThan(0);
  });

  it("lets the pharmacist cancel a held draft so it is not sent", async () => {
    const user = userEvent.setup();
    vi.spyOn(triageApi, "listTriageItems").mockResolvedValue({
      items: [OPEN_ITEM],
    } satisfies TriageItemList);
    vi.spyOn(treatmentsApi, "listConversationMessages").mockResolvedValue(CONVERSATION_MESSAGES);
    vi.spyOn(triageApi, "updateTriageItemStatus").mockResolvedValueOnce({
      ...OPEN_ITEM,
      status: "acknowledged",
    });
    const rejectSpy = vi.spyOn(triageApi, "rejectTriageItem").mockResolvedValue({
      triage_item: { ...OPEN_ITEM, status: "resolved" },
      rejected_message: {
        ...CONVERSATION_MESSAGES.items[1],
        status: "rejected",
      },
    });

    renderPage();

    await screen.findByText("Clinical draft review");
    await user.click(screen.getByRole("button", { name: /review item/i }));
    await user.click(screen.getByRole("button", { name: /start review item/i }));
    await user.click(screen.getByRole("button", { name: /cancel draft item/i }));

    await waitFor(() => expect(rejectSpy).toHaveBeenCalledWith("triage-1"));
    expect(screen.getAllByText("Resolved").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Canceled, not sent").length).toBeGreaterThan(0);
  });

  it("shows a calm empty state when no patients need review", async () => {
    vi.spyOn(triageApi, "listTriageItems").mockResolvedValue({ items: [] });

    renderPage();

    await screen.findByText(/no patients need review right now/i);
    expect(screen.queryByText(/could not load/i)).toBeNull();
  });

  it("expands a triage item and displays its conversation context", async () => {
    const user = userEvent.setup();
    vi.spyOn(triageApi, "listTriageItems").mockResolvedValue({
      items: [OPEN_ITEM],
    });
    const conversationSpy = vi
      .spyOn(treatmentsApi, "listConversationMessages")
      .mockResolvedValue(CONVERSATION_MESSAGES);

    renderPage();

    await screen.findByText("Clinical draft review");
    await user.click(screen.getByRole("button", { name: /review item/i }));

    await waitFor(() =>
      expect(conversationSpy).toHaveBeenCalledWith(OPEN_ITEM.treatment_id, {
        limit: 100,
        offset: 0,
      }),
    );
    expect(screen.getByText("Pharmacist review")).toBeTruthy();
    expect(screen.getByRole("button", { name: /start review item/i })).toBeTruthy();
    expect(screen.getByRole("button", { name: /back to queue/i })).toBeTruthy();
    expect(screen.getByText("Flag Summary")).toBeTruthy();
    expect(screen.getByText("Patient conversation")).toBeTruthy();
    expect(screen.getAllByText("Held for review").length).toBeGreaterThan(0);
    expect(screen.getByText("Approve draft or resolve manually")).toBeTruthy();
    expect(screen.getByText("Patient message")).toBeTruthy();
    expect(screen.getByText("Held assistant draft")).toBeTruthy();
    expect(screen.getAllByText("I feel dizzy after the second dose.").length).toBeGreaterThan(0);
    expect(screen.getAllByText("You can skip the next dose.").length).toBeGreaterThan(0);
    expect(screen.getByText("Held draft, not sent")).toBeTruthy();
  });

  it("hides patient conversation bodies when privacy mode is active", async () => {
    const user = userEvent.setup();
    vi.spyOn(triageApi, "listTriageItems").mockResolvedValue({
      items: [OPEN_ITEM],
    });
    vi.spyOn(treatmentsApi, "listConversationMessages").mockResolvedValue(CONVERSATION_MESSAGES);

    renderPage({ isPrivacyMode: true });

    await screen.findByText("Clinical draft review");
    await user.click(screen.getByRole("button", { name: /review item/i }));

    expect(await screen.findAllByText("Message hidden in privacy mode.")).toHaveLength(4);
    expect(screen.queryByText("I feel dizzy after the second dose.")).toBeNull();
    expect(screen.queryByText("You can skip the next dose.")).toBeNull();
  });

  it("shows pharmacist-facing wording for draft review hold reasons", async () => {
    const user = userEvent.setup();
    const draftReviewItem: TriageItemView = {
      ...OPEN_ITEM,
      reason: "dose_change_request",
    };
    vi.spyOn(triageApi, "listTriageItems").mockResolvedValue({
      items: [draftReviewItem],
    });
    vi.spyOn(treatmentsApi, "listConversationMessages").mockResolvedValue({
      items: [
        CONVERSATION_MESSAGES.items[0],
        {
          ...CONVERSATION_MESSAGES.items[1],
          safety_hold_reason: "draft_requires_review",
        },
      ],
    });

    renderPage();

    await screen.findByText("Dose-change request");
    await user.click(screen.getByRole("button", { name: /review item/i }));

    await screen.findByText("Flag Summary");
    expect(screen.getAllByText(/Draft needs pharmacist review/).length).toBeGreaterThan(0);
    expect(screen.queryByText(/draft_requires_review/)).toBeNull();
  });
});
