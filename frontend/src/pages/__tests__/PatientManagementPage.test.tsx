import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { toast } from "sonner";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as treatmentsApi from "../../api/treatments";
import * as triageApi from "../../api/triage";
import type {
  ConversationMessageList,
  ConversationTurnView,
  TreatmentDetail,
  TreatmentList,
} from "../../api/treatments";
import type { TriageItemList } from "../../api/triage";
import PatientManagementPage from "../PatientManagementPage";

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

const TREATMENTS: TreatmentList = {
  items: [
    {
      patient: {
        id: "patient-1",
        name: "Eleanor Vance",
        dob: "1955-10-12",
        mrn: "PHA-AB12",
        phone: "+18005551212",
        allergies: ["Sulfa"],
      },
      treatment: {
        id: "22222222-2222-2222-2222-222222222222",
        patient_id: "patient-1",
        status: "pending",
        chat_response_mode: "ai_active",
        automation_mode: "active",
        clinical_objective: "Monitor dizziness",
        treatment_start_at: "2026-05-16T08:30:00Z",
        created_at: "2026-05-15T09:00:00Z",
      },
      medication_count: 2,
      first_medication_name: "Lisinopril",
    },
    {
      patient: {
        id: "patient-1",
        name: "Eleanor Vance",
        dob: "1955-10-12",
        mrn: "PHA-AB12",
        phone: "+18005551212",
        allergies: ["Sulfa"],
      },
      treatment: {
        id: "33333333-3333-3333-3333-333333333333",
        patient_id: "patient-1",
        status: "active",
        chat_response_mode: "ai_active",
        automation_mode: "active",
        clinical_objective: "Monitor glucose",
        treatment_start_at: "2026-05-17T08:30:00Z",
        created_at: "2026-05-14T09:00:00Z",
      },
      medication_count: 1,
      first_medication_name: "Metformin",
    },
  ],
};

const MESSAGES: ConversationMessageList = {
  items: [
    {
      id: "msg-1",
      treatment_id: TREATMENTS.items[0].treatment.id,
      direction: "inbound",
      sender_type: "patient",
      channel: "whatsapp",
      status: "received",
      body: "I feel dizzy today.",
      safety_hold_reason: null,
      external_message_id: null,
      created_at: "2026-05-15T10:00:00Z",
    },
  ],
};

const TAKEOVER_TREATMENTS: TreatmentList = {
  items: [
    {
      ...TREATMENTS.items[0],
      treatment: {
        ...TREATMENTS.items[0].treatment,
        chat_response_mode: "pharmacist_takeover",
      },
    },
  ],
};

const DETAIL: TreatmentDetail = {
  patient: TREATMENTS.items[0].patient,
  treatment: TREATMENTS.items[0].treatment,
  medications: [
    {
      id: "med-1",
      name: "Lisinopril",
      dosage: "10mg",
      frequency: "Once daily",
      duration: "30 days",
      objective: "Monitor dizziness",
      ordinal: 0,
    },
    {
      id: "med-2",
      name: "Amlodipine",
      dosage: "5mg",
      frequency: "Once daily",
      duration: "30 days",
      objective: null,
      ordinal: 1,
    },
  ],
};

const TAKEOVER_DETAIL: TreatmentDetail = {
  ...DETAIL,
  treatment: TAKEOVER_TREATMENTS.items[0].treatment,
};

const HELD_TURN: ConversationTurnView = {
  inbound_message: {
    ...MESSAGES.items[0],
    id: "msg-2",
    body: "Can I stop the medicine?",
  },
  assistant_message: {
    id: "msg-3",
    treatment_id: TREATMENTS.items[0].treatment.id,
    direction: "outbound",
    sender_type: "assistant",
    channel: "whatsapp",
    status: "held_for_review",
    body: "You can stop it now.",
    safety_hold_reason: "referee",
    external_message_id: null,
    created_at: "2026-05-15T10:01:00Z",
  },
  safety_decision: {
    status: "hold_for_pharmacist",
    message_to_send: null,
    hold_reason: "referee",
  },
};

const PHARMACIST_MESSAGE = {
  id: "msg-pharmacist",
  treatment_id: TREATMENTS.items[0].treatment.id,
  direction: "outbound" as const,
  sender_type: "pharmacist" as const,
  channel: "whatsapp" as const,
  status: "queued" as const,
  body: "Please continue the current dose.",
  safety_hold_reason: null,
  external_message_id: null,
  created_at: "2026-05-15T10:03:00Z",
};

const TRIAGE_ITEMS: TriageItemList = {
  items: [
    {
      id: "triage-1",
      treatment_id: TREATMENTS.items[0].treatment.id,
      conversation_message_id: "msg-3",
      reason: "referee",
      status: "open",
      created_at: "2026-05-15T10:02:00Z",
    },
  ],
};

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/dashboard/surveillance"]}>
      <Routes>
        <Route element={<Outlet context={{ isPrivacyMode: false }} />}>
          <Route path="/dashboard/surveillance" element={<PatientManagementPage />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.clearAllMocks();
});

describe("PatientManagementPage", () => {
  it("loads treatments and conversation messages from the API", async () => {
    vi.spyOn(treatmentsApi, "listTreatments").mockResolvedValue(TREATMENTS);
    vi.spyOn(treatmentsApi, "getTreatment").mockResolvedValue(DETAIL);
    vi.spyOn(treatmentsApi, "listConversationMessages").mockResolvedValue(MESSAGES);
    vi.spyOn(triageApi, "listTriageItems").mockResolvedValue(TRIAGE_ITEMS);

    renderPage();

    await screen.findByText("Eleanor Vance");
    expect(screen.getAllByText(/PHA-AB12/).length).toBeGreaterThan(0);
    expect(screen.getByText("2 treatments")).toBeTruthy();
    expect(screen.getByText(/First listed medication: Lisinopril/)).toBeTruthy();
    expect(screen.getByText("Lisinopril + 1 more")).toBeTruthy();
    expect(screen.getAllByText("Monitor dizziness").length).toBeGreaterThan(0);
    expect(screen.getByText("Metformin")).toBeTruthy();
    expect(screen.getByText("Monitor glucose")).toBeTruthy();
    expect(await screen.findByRole("columnheader", { name: "Dosage" })).toBeTruthy();
    expect(screen.getByText("10mg")).toBeTruthy();
    expect(screen.getByText("Amlodipine")).toBeTruthy();
    expect(await screen.findByText("Needs pharmacist review")).toBeTruthy();
    expect(screen.getByText("Clinical draft review")).toBeTruthy();
    expect(screen.getByRole("link", { name: /open triage queue/i })).toHaveAttribute(
      "href",
      "/dashboard/triage",
    );
    expect(await screen.findByText("I feel dizzy today.")).toBeTruthy();
  });

  it("submits an incoming WhatsApp message and refreshes the thread", async () => {
    const user = userEvent.setup();
    vi.spyOn(treatmentsApi, "listTreatments").mockResolvedValue(TREATMENTS);
    vi.spyOn(treatmentsApi, "getTreatment").mockResolvedValue(DETAIL);
    vi.spyOn(triageApi, "listTriageItems").mockResolvedValue(TRIAGE_ITEMS);
    vi.spyOn(treatmentsApi, "listConversationMessages")
      .mockResolvedValueOnce(MESSAGES)
      .mockResolvedValueOnce({
        items: [...MESSAGES.items, HELD_TURN.inbound_message, HELD_TURN.assistant_message],
      });
    const draftSpy = vi
      .spyOn(treatmentsApi, "draftPatientReply")
      .mockResolvedValue(HELD_TURN);

    renderPage();

    await screen.findByText("I feel dizzy today.");
    await user.type(
      screen.getByLabelText(/incoming whatsapp message/i),
      "Can I stop the medicine?",
    );
    await user.click(screen.getByRole("button", { name: /process incoming message/i }));

    await waitFor(() =>
      expect(draftSpy).toHaveBeenCalledWith(TREATMENTS.items[0].treatment.id, {
        patient_message: "Can I stop the medicine?",
      }),
    );
    await screen.findByText("You can stop it now.");
    expect(toast.success).toHaveBeenCalledWith("Draft held for pharmacist review", {
      description: "The item is now available in the triage queue.",
    });
  });

  it("queues a pharmacist WhatsApp message from the chat panel", async () => {
    const user = userEvent.setup();
    vi.spyOn(treatmentsApi, "listTreatments").mockResolvedValue(TREATMENTS);
    vi.spyOn(treatmentsApi, "getTreatment").mockResolvedValue(DETAIL);
    vi.spyOn(triageApi, "listTriageItems").mockResolvedValue(TRIAGE_ITEMS);
    vi.spyOn(treatmentsApi, "listConversationMessages")
      .mockResolvedValueOnce(MESSAGES)
      .mockResolvedValueOnce({
        items: [...MESSAGES.items, PHARMACIST_MESSAGE],
      });
    const sendSpy = vi
      .spyOn(treatmentsApi, "sendPharmacistMessage")
      .mockResolvedValue(PHARMACIST_MESSAGE);

    renderPage();

    await screen.findByText("I feel dizzy today.");
    await user.type(
      screen.getByLabelText(/pharmacist whatsapp message/i),
      "Please continue the current dose.",
    );
    await user.click(screen.getByRole("button", { name: /send pharmacist message/i }));

    await waitFor(() =>
      expect(sendSpy).toHaveBeenCalledWith(TREATMENTS.items[0].treatment.id, {
        message: "Please continue the current dose.",
      }),
    );
    await screen.findByText("Please continue the current dose.");
    expect(toast.success).toHaveBeenCalledWith("Pharmacist message queued", {
      description: "It will be sent through the WhatsApp delivery workflow.",
    });
  });

  it("lets the pharmacist resume AI replies from takeover mode", async () => {
    const user = userEvent.setup();
    vi.spyOn(treatmentsApi, "listTreatments").mockResolvedValue(TAKEOVER_TREATMENTS);
    vi.spyOn(treatmentsApi, "getTreatment").mockResolvedValue(TAKEOVER_DETAIL);
    vi.spyOn(treatmentsApi, "listConversationMessages").mockResolvedValue(MESSAGES);
    vi.spyOn(triageApi, "listTriageItems").mockResolvedValue(TRIAGE_ITEMS);
    const updateSpy = vi
      .spyOn(treatmentsApi, "updateTreatmentChatResponseMode")
      .mockResolvedValue({
        ...TAKEOVER_TREATMENTS.items[0].treatment,
        chat_response_mode: "ai_active",
      });

    renderPage();

    await screen.findByText("Pharmacist replying");
    await user.click(screen.getByRole("button", { name: /resume ai replies/i }));

    await waitFor(() =>
      expect(updateSpy).toHaveBeenCalledWith(TAKEOVER_TREATMENTS.items[0].treatment.id, {
        chat_response_mode: "ai_active",
      }),
    );
    expect(await screen.findByText("AI replying")).toBeTruthy();
    expect(toast.success).toHaveBeenCalledWith("AI replies resumed", {
      description: "The agent can draft future patient replies for this treatment.",
    });
  });
});
