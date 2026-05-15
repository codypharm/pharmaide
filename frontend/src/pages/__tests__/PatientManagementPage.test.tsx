import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { toast } from "sonner";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as treatmentsApi from "../../api/treatments";
import type {
  ConversationMessageList,
  ConversationTurnView,
  TreatmentList,
} from "../../api/treatments";
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
    vi.spyOn(treatmentsApi, "listConversationMessages").mockResolvedValue(MESSAGES);

    renderPage();

    await screen.findByText("Eleanor Vance");
    expect(screen.getAllByText(/PHA-AB12/).length).toBeGreaterThan(0);
    expect(screen.getByText("2 treatments")).toBeTruthy();
    expect(screen.getByText(/First listed medication: Lisinopril/)).toBeTruthy();
    expect(screen.getAllByText("Lisinopril").length).toBeGreaterThan(0);
    expect(screen.getByText("Metformin")).toBeTruthy();
    expect(await screen.findByText("I feel dizzy today.")).toBeTruthy();
  });

  it("submits an incoming WhatsApp message and refreshes the thread", async () => {
    const user = userEvent.setup();
    vi.spyOn(treatmentsApi, "listTreatments").mockResolvedValue(TREATMENTS);
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
});
