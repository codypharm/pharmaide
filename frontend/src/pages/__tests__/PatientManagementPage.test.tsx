import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { toast } from "sonner";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as treatmentsApi from "../../api/treatments";
import * as triageApi from "../../api/triage";
import type {
  ConversationMessageList,
  ConversationTurnView,
  PatientCheckInList,
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

const TREATMENTS_WITH_COMPLETED: TreatmentList = {
  items: [
    TREATMENTS.items[0],
    {
      patient: {
        id: "patient-2",
        name: "Marcus Chen",
        dob: "1974-04-02",
        mrn: "PHA-MC77",
        phone: "+18005559876",
        allergies: [],
      },
      treatment: {
        id: "44444444-4444-4444-4444-444444444444",
        patient_id: "patient-2",
        status: "completed",
        chat_response_mode: "ai_active",
        automation_mode: "active",
        clinical_objective: "Monitor recovery",
        treatment_start_at: "2026-05-01T08:30:00Z",
        created_at: "2026-05-01T09:00:00Z",
      },
      medication_count: 1,
      first_medication_name: "Amoxicillin",
    },
    {
      patient: {
        id: "patient-3",
        name: "Priya Shah",
        dob: "1981-09-18",
        mrn: "PHA-PS18",
        phone: "+18005550118",
        allergies: [],
      },
      treatment: {
        id: "55555555-5555-5555-5555-555555555555",
        patient_id: "patient-3",
        status: "completed",
        chat_response_mode: "ai_active",
        automation_mode: "active",
        clinical_objective: "Monitor pain resolution",
        treatment_start_at: "2026-04-20T08:30:00Z",
        archived_at: "2026-05-20T12:00:00Z",
        created_at: "2026-04-20T09:00:00Z",
      },
      medication_count: 1,
      first_medication_name: "Ibuprofen",
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

const SENT_ASSISTANT_MESSAGE = {
  id: "msg-sent",
  treatment_id: TREATMENTS.items[0].treatment.id,
  direction: "outbound" as const,
  sender_type: "assistant" as const,
  channel: "whatsapp" as const,
  status: "sent" as const,
  body: "Please take the next dose with water.",
  safety_hold_reason: null,
  external_message_id: "whatsapp-msg-1",
  created_at: "2026-05-15T10:04:00Z",
};

const APPROVED_ASSISTANT_MESSAGE = {
  id: "msg-approved",
  treatment_id: TREATMENTS.items[0].treatment.id,
  direction: "outbound" as const,
  sender_type: "assistant" as const,
  channel: "whatsapp" as const,
  status: "approved" as const,
  body: "Your pharmacist has approved this response.",
  safety_hold_reason: null,
  external_message_id: null,
  created_at: "2026-05-15T10:04:15Z",
};

const READY_ASSISTANT_MESSAGE = {
  id: "msg-ready",
  treatment_id: TREATMENTS.items[0].treatment.id,
  direction: "outbound" as const,
  sender_type: "assistant" as const,
  channel: "whatsapp" as const,
  status: "draft_ready" as const,
  body: "Your pharmacist is reviewing this and will update you.",
  safety_hold_reason: null,
  external_message_id: null,
  created_at: "2026-05-15T10:04:30Z",
};

const CANCELED_ASSISTANT_MESSAGE = {
  id: "msg-canceled",
  treatment_id: TREATMENTS.items[0].treatment.id,
  direction: "outbound" as const,
  sender_type: "assistant" as const,
  channel: "whatsapp" as const,
  status: "rejected" as const,
  body: "You can stop it now.",
  safety_hold_reason: "referee",
  external_message_id: null,
  created_at: "2026-05-15T10:04:45Z",
};

const FAILED_PHARMACIST_MESSAGE = {
  id: "msg-failed",
  treatment_id: TREATMENTS.items[0].treatment.id,
  direction: "outbound" as const,
  sender_type: "pharmacist" as const,
  channel: "whatsapp" as const,
  status: "failed" as const,
  body: "Please call the pharmacy today.",
  safety_hold_reason: null,
  external_message_id: null,
  created_at: "2026-05-15T10:05:00Z",
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

const PATIENT_UPDATES: PatientCheckInList = {
  items: [
    {
      id: "check-in-1",
      treatment_id: TREATMENTS.items[0].treatment.id,
      report_type: "not_improving",
      source: "patient",
      message: "Pain has not improved since yesterday.",
      observed_at: "2026-05-15T08:30:00Z",
      created_at: "2026-05-15T10:10:00Z",
    },
    {
      id: "check-in-2",
      treatment_id: TREATMENTS.items[0].treatment.id,
      report_type: "side_effect",
      source: "pharmacist",
      message: "Patient reported mild dizziness during callback.",
      observed_at: null,
      created_at: "2026-05-15T10:20:00Z",
    },
  ],
};

const EMPTY_PATIENT_UPDATES: PatientCheckInList = {
  items: [],
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

beforeEach(() => {
  vi.spyOn(treatmentsApi, "listPatientCheckIns").mockResolvedValue(EMPTY_PATIENT_UPDATES);
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.clearAllMocks();
});

describe("PatientManagementPage", () => {
  it("scrolls patient-facing chat to the latest message after loading", async () => {
    const scrollIntoView = vi.fn();
    window.HTMLElement.prototype.scrollIntoView = scrollIntoView;
    vi.spyOn(treatmentsApi, "listTreatments").mockResolvedValue(TREATMENTS);
    vi.spyOn(treatmentsApi, "getTreatment").mockResolvedValue(DETAIL);
    vi.spyOn(treatmentsApi, "listConversationMessages").mockResolvedValue({
      items: [...MESSAGES.items, SENT_ASSISTANT_MESSAGE],
    });
    vi.spyOn(triageApi, "listTriageItems").mockResolvedValue({ items: [] });

    renderPage();

    await screen.findByText("Please take the next dose with water.");

    await waitFor(() =>
      expect(scrollIntoView).toHaveBeenCalledWith({
        block: "end",
        behavior: "auto",
      }),
    );
  });

  it("loads treatments and conversation messages from the API", async () => {
    vi.spyOn(treatmentsApi, "listTreatments").mockResolvedValue(TREATMENTS);
    vi.spyOn(treatmentsApi, "getTreatment").mockResolvedValue(DETAIL);
    vi.spyOn(treatmentsApi, "listConversationMessages").mockResolvedValue(MESSAGES);
    vi.spyOn(treatmentsApi, "listPatientCheckIns").mockResolvedValue(PATIENT_UPDATES);
    vi.spyOn(triageApi, "listTriageItems").mockResolvedValue(TRIAGE_ITEMS);

    renderPage();

    await screen.findByText("Eleanor Vance");
    expect(screen.getAllByText(/PHA-AB12/).length).toBeGreaterThan(0);
    expect(screen.getByText("2 treatments")).toBeTruthy();
    expect(screen.getByText(/First listed medication: Lisinopril/)).toBeTruthy();
    expect(screen.getByText("Lisinopril + 1 more")).toBeTruthy();
    expect(screen.getByText("1 flag")).toBeTruthy();
    expect(screen.getAllByText("Monitor dizziness").length).toBeGreaterThan(0);
    expect(screen.getByText("Metformin")).toBeTruthy();
    expect(screen.getByText("Monitor glucose")).toBeTruthy();
    expect(await screen.findByRole("columnheader", { name: "Dosage" })).toBeTruthy();
    expect(screen.getByText("10mg")).toBeTruthy();
    expect(screen.getByText("Amlodipine")).toBeTruthy();
    expect(screen.getByText("Amlodipine").closest("td")).toHaveAttribute("title", "Amlodipine");
    expect(screen.getByText("Amlodipine").closest("td")?.className).toContain("break-words");
    expect(await screen.findByText("Needs pharmacist review")).toBeTruthy();
    expect(await screen.findByText("Patient Updates")).toBeTruthy();
    expect(screen.getByText("Pain has not improved since yesterday.")).toBeTruthy();
    expect(screen.getByText("Not Improving")).toBeTruthy();
    expect(screen.getByText("Patient")).toBeTruthy();
    expect(screen.getByText("Patient reported mild dizziness during callback.")).toBeTruthy();
    expect(screen.getByText("Side Effect")).toBeTruthy();
    expect(screen.getByText("Pharmacist")).toBeTruthy();
    expect(screen.getByText("Clinical draft review")).toBeTruthy();
    expect(screen.getByRole("link", { name: /open triage queue/i })).toHaveAttribute(
      "href",
      "/dashboard/triage",
    );
    const patientMessage = await screen.findByText("I feel dizzy today.");
    expect(patientMessage.closest("[data-message-side]")).toHaveAttribute(
      "data-message-side",
      "left",
    );
  });

  it("separates completed treatments and links them to the report view", async () => {
    const user = userEvent.setup();
    vi.spyOn(treatmentsApi, "listTreatments").mockResolvedValue(TREATMENTS_WITH_COMPLETED);
    vi.spyOn(treatmentsApi, "getTreatment").mockResolvedValue(DETAIL);
    vi.spyOn(treatmentsApi, "listConversationMessages").mockResolvedValue(MESSAGES);
    vi.spyOn(triageApi, "listTriageItems").mockResolvedValue({ items: [] });

    renderPage();

    const directory = screen.getByRole("complementary", { name: /patient directory/i });
    await within(directory).findByText("Eleanor Vance");
    expect(within(directory).queryByText("Marcus Chen")).toBeNull();

    await user.click(screen.getByRole("tab", { name: /completed/i }));

    expect(await within(directory).findByText("Marcus Chen")).toBeTruthy();
    expect(within(directory).getByText("Amoxicillin")).toBeTruthy();
    expect(within(directory).queryByText("Eleanor Vance")).toBeNull();
    expect(within(directory).queryByText("Priya Shah")).toBeNull();
    expect(within(directory).getByRole("link", { name: /view report/i })).toHaveAttribute(
      "href",
      "/dashboard/treatments/44444444-4444-4444-4444-444444444444",
    );

    await user.click(screen.getByRole("tab", { name: /archived/i }));

    expect(await within(directory).findByText("Priya Shah")).toBeTruthy();
    expect(within(directory).getByText("Ibuprofen")).toBeTruthy();
    expect(within(directory).queryByText("Marcus Chen")).toBeNull();
    expect(within(directory).getByRole("link", { name: /view report/i })).toHaveAttribute(
      "href",
      "/dashboard/treatments/55555555-5555-5555-5555-555555555555",
    );
  });

  it("lets the pharmacist update the treatment objective", async () => {
    const user = userEvent.setup();
    vi.spyOn(treatmentsApi, "listTreatments").mockResolvedValue(TREATMENTS);
    vi.spyOn(treatmentsApi, "getTreatment").mockResolvedValue(DETAIL);
    vi.spyOn(treatmentsApi, "listConversationMessages").mockResolvedValue(MESSAGES);
    vi.spyOn(triageApi, "listTriageItems").mockResolvedValue(TRIAGE_ITEMS);
    const updateSpy = vi
      .spyOn(treatmentsApi, "updateTreatmentClinicalObjective")
      .mockResolvedValue({
        ...TREATMENTS.items[0].treatment,
        clinical_objective: "Monitor nausea and recovery",
      });

    renderPage();

    const objective = await screen.findByLabelText(/treatment objective/i);
    await user.clear(objective);
    await user.type(objective, "Monitor nausea and recovery");
    await user.click(screen.getByRole("button", { name: /save objective/i }));

    await waitFor(() =>
      expect(updateSpy).toHaveBeenCalledWith(TREATMENTS.items[0].treatment.id, {
        clinical_objective: "Monitor nausea and recovery",
      }),
    );
    expect(await screen.findByDisplayValue("Monitor nausea and recovery")).toBeTruthy();
    expect(toast.success).toHaveBeenCalledWith("Treatment objective updated", {
      description: "Monitoring context now reflects the saved objective.",
    });
  });

  it("shows real safety flag context in the safety review tab", async () => {
    const user = userEvent.setup();
    vi.spyOn(treatmentsApi, "listTreatments").mockResolvedValue(TREATMENTS);
    vi.spyOn(treatmentsApi, "getTreatment").mockResolvedValue(DETAIL);
    vi.spyOn(treatmentsApi, "listConversationMessages").mockResolvedValue({
      items: [...MESSAGES.items, HELD_TURN.assistant_message],
    });
    vi.spyOn(triageApi, "listTriageItems").mockResolvedValue(TRIAGE_ITEMS);

    renderPage();

    await screen.findByText("I feel dizzy today.");
    await user.click(screen.getByRole("button", { name: /safety review/i }));

    expect(await screen.findByText("Active Safety Flags")).toBeTruthy();
    expect(screen.getAllByText("Clinical draft review").length).toBeGreaterThan(1);
    expect(screen.getByText("Open")).toBeTruthy();
    expect(screen.getByText("Held draft")).toBeTruthy();
    expect(screen.getByText("You can stop it now.")).toBeTruthy();
  });

  it("opens safety review when the treatment flag badge is clicked", async () => {
    const user = userEvent.setup();
    vi.spyOn(treatmentsApi, "listTreatments").mockResolvedValue(TREATMENTS);
    vi.spyOn(treatmentsApi, "getTreatment").mockResolvedValue(DETAIL);
    vi.spyOn(treatmentsApi, "listConversationMessages").mockResolvedValue({
      items: [...MESSAGES.items, HELD_TURN.assistant_message],
    });
    vi.spyOn(triageApi, "listTriageItems").mockResolvedValue(TRIAGE_ITEMS);

    renderPage();

    await screen.findByText("I feel dizzy today.");
    await user.click(screen.getByText("1 flag"));

    expect(await screen.findByText("Active Safety Flags")).toBeTruthy();
    expect(screen.getByText("Held draft")).toBeTruthy();
  });

  it("submits an incoming WhatsApp message and refreshes the thread", async () => {
    const user = userEvent.setup();
    vi.spyOn(treatmentsApi, "listTreatments").mockResolvedValue(TREATMENTS);
    vi.spyOn(treatmentsApi, "getTreatment").mockResolvedValue(DETAIL);
    vi.spyOn(triageApi, "listTriageItems")
      .mockResolvedValueOnce({ items: [] })
      .mockResolvedValueOnce(TRIAGE_ITEMS);
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
      screen.getByLabelText(/test patient whatsapp message/i),
      "Can I stop the medicine?",
    );
    await user.click(screen.getByRole("button", { name: /process test patient message/i }));

    await waitFor(() =>
      expect(draftSpy).toHaveBeenCalledWith(TREATMENTS.items[0].treatment.id, {
        patient_message: "Can I stop the medicine?",
      }),
    );
    await screen.findByText("You can stop it now.");
    expect(toast.success).toHaveBeenCalledWith("Draft held for pharmacist review", {
      description: "The item is now available in the triage queue.",
    });
    expect(screen.getByText("Held, not sent")).toBeTruthy();
    expect(screen.getByText("1 flag")).toBeTruthy();
  });

  it("marks ready assistant drafts as not sent in the internal chat log", async () => {
    vi.spyOn(treatmentsApi, "listTreatments").mockResolvedValue(TREATMENTS);
    vi.spyOn(treatmentsApi, "getTreatment").mockResolvedValue(DETAIL);
    vi.spyOn(treatmentsApi, "listConversationMessages").mockResolvedValue({
      items: [...MESSAGES.items, READY_ASSISTANT_MESSAGE],
    });
    vi.spyOn(triageApi, "listTriageItems").mockResolvedValue({ items: [] });

    renderPage();

    await screen.findByText("Your pharmacist is reviewing this and will update you.");
    expect(screen.getByText("Ready, not sent")).toBeTruthy();
    expect(screen.queryByText("1 flag")).toBeNull();
  });

  it("marks canceled assistant drafts as not sent in the internal chat log", async () => {
    vi.spyOn(treatmentsApi, "listTreatments").mockResolvedValue(TREATMENTS);
    vi.spyOn(treatmentsApi, "getTreatment").mockResolvedValue(DETAIL);
    vi.spyOn(treatmentsApi, "listConversationMessages").mockResolvedValue({
      items: [...MESSAGES.items, CANCELED_ASSISTANT_MESSAGE],
    });
    vi.spyOn(triageApi, "listTriageItems").mockResolvedValue({ items: [] });

    renderPage();

    await screen.findByText("You can stop it now.");
    expect(screen.getByText("Canceled, not sent")).toBeTruthy();
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
    const pharmacistBubble = await screen.findByText("Please continue the current dose.");
    expect(pharmacistBubble.closest("[data-message-side]")).toHaveAttribute(
      "data-message-side",
      "right",
    );
    expect(screen.getByText("Waiting to send")).toBeTruthy();
    expect(toast.success).toHaveBeenCalledWith("Pharmacist message queued", {
      description: "It will be sent through the WhatsApp delivery workflow.",
    });
  });

  it("shows outbound WhatsApp delivery state and retries failed messages", async () => {
    const user = userEvent.setup();
    vi.spyOn(treatmentsApi, "listTreatments").mockResolvedValue(TREATMENTS);
    vi.spyOn(treatmentsApi, "getTreatment").mockResolvedValue(DETAIL);
    vi.spyOn(triageApi, "listTriageItems").mockResolvedValue(TRIAGE_ITEMS);
    vi.spyOn(treatmentsApi, "listConversationMessages")
      .mockResolvedValueOnce({
        items: [
          ...MESSAGES.items,
          PHARMACIST_MESSAGE,
          SENT_ASSISTANT_MESSAGE,
          APPROVED_ASSISTANT_MESSAGE,
          FAILED_PHARMACIST_MESSAGE,
        ],
      })
      .mockResolvedValueOnce({
        items: [
          ...MESSAGES.items,
          PHARMACIST_MESSAGE,
          SENT_ASSISTANT_MESSAGE,
          APPROVED_ASSISTANT_MESSAGE,
          { ...FAILED_PHARMACIST_MESSAGE, status: "queued" },
        ],
      });
    const retrySpy = vi
      .spyOn(treatmentsApi, "retryConversationMessageDelivery")
      .mockResolvedValue({ ...FAILED_PHARMACIST_MESSAGE, status: "queued" });

    renderPage();

    await screen.findByText("Please continue the current dose.");
    expect(screen.getByText("Waiting to send")).toBeTruthy();
    expect(screen.getByText("Approved, not sent")).toBeTruthy();
    expect(screen.getByText("Sent")).toBeTruthy();
    expect(screen.getByText("Send failed")).toBeTruthy();
    expect(screen.getAllByRole("button", { name: /retry send/i })).toHaveLength(1);
    await user.click(screen.getByRole("button", { name: /retry send/i }));

    await waitFor(() =>
      expect(retrySpy).toHaveBeenCalledWith(
        TREATMENTS.items[0].treatment.id,
        FAILED_PHARMACIST_MESSAGE.id,
      ),
    );
    expect(toast.success).toHaveBeenCalledWith("Message queued again", {
      description: "The delivery workflow will attempt to send it again.",
    });
  });

  it("auto-refreshes the selected conversation while surveillance is open", async () => {
    vi.useFakeTimers();
    vi.spyOn(treatmentsApi, "listTreatments").mockResolvedValue(TREATMENTS);
    vi.spyOn(treatmentsApi, "getTreatment").mockResolvedValue(DETAIL);
    const listTriageSpy = vi.spyOn(triageApi, "listTriageItems").mockResolvedValue(TRIAGE_ITEMS);
    const listConversationSpy = vi
      .spyOn(treatmentsApi, "listConversationMessages")
      .mockResolvedValueOnce(MESSAGES)
      .mockResolvedValueOnce({
        items: [...MESSAGES.items, SENT_ASSISTANT_MESSAGE],
      });

    renderPage();

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(screen.getByText("I feel dizzy today.")).toBeTruthy();
    expect(screen.queryByText("Please take the next dose with water.")).toBeNull();

    await act(async () => {
      vi.advanceTimersByTime(10_000);
      await Promise.resolve();
    });

    expect(screen.getByText("Please take the next dose with water.")).toBeTruthy();
    expect(listConversationSpy).toHaveBeenCalledTimes(2);
    expect(listTriageSpy).toHaveBeenCalledTimes(2);
    expect(screen.getByText(/^Updated /)).toBeTruthy();
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

    await screen.findByText("Pharmacist");
    expect(screen.queryByText("Conversation control")).toBeNull();
    expect(screen.queryByText("Chat manual")).toBeNull();
    expect(screen.queryByText(/scheduled reminders and check-ins continue/i)).toBeNull();
    await user.click(screen.getByRole("switch", { name: /chat reply mode/i }));

    await waitFor(() =>
      expect(updateSpy).toHaveBeenCalledWith(TAKEOVER_TREATMENTS.items[0].treatment.id, {
        chat_response_mode: "ai_active",
      }),
    );
    expect(await screen.findByText("Agent")).toBeTruthy();
    expect(toast.success).toHaveBeenCalledWith("AI replies resumed", {
      description: "The agent can draft future patient replies for this treatment.",
    });
  });
});
