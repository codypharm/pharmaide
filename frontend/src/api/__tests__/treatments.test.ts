import { afterEach, describe, expect, it, vi } from "vitest";
import {
  createAdherenceEvent,
  createPatientCheckIn,
  draftPatientReply,
  getAnalysis,
  listAdherenceEvents,
  listConversationMessages,
  listPatientCheckIns,
  listTreatments,
  triggerAnalysis,
} from "../treatments";

function mockFetch(response: { status: number; body: unknown }) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = typeof input === "string" ? input : (input as Request).url;
    const body =
      response.status === 204
        ? null
        : JSON.stringify({ ...(response.body as object), _url: url });
    return new Response(body, {
      status: response.status,
      headers: new Headers({ "X-Request-ID": "req_test" }),
    });
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("listTreatments", () => {
  it("calls /treatments with no query params by default", async () => {
    const spy = mockFetch({ status: 200, body: { items: [] } });
    await listTreatments();

    const calledUrl = spy.mock.calls[0]?.[0] as string;
    expect(calledUrl).toMatch(/\/treatments$/);
  });

  it("passes limit and offset through as query params", async () => {
    const spy = mockFetch({ status: 200, body: { items: [] } });
    await listTreatments({ limit: 25, offset: 50 });

    const calledUrl = spy.mock.calls[0]?.[0] as string;
    expect(calledUrl).toContain("limit=25");
    expect(calledUrl).toContain("offset=50");
  });

  it("returns the parsed items array on success", async () => {
    mockFetch({
      status: 200,
      body: {
        items: [
          {
            patient: {
              id: "p1",
              name: "Eleanor",
              dob: "1955-10-12",
              mrn: "M1",
              phone: "+1",
              allergies: [],
            },
            treatment: {
              id: "t1",
              patient_id: "p1",
              status: "pending",
              chat_response_mode: "ai_active",
              automation_mode: "active",
              clinical_objective: null,
              treatment_start_at: null,
              created_at: "2026-05-11T12:00:00Z",
            },
            medication_count: 2,
            first_medication_name: "Lisinopril",
          },
        ],
      },
    });

    const result = await listTreatments();
    expect(result.items).toHaveLength(1);
    expect(result.items[0].medication_count).toBe(2);
    expect(result.items[0].first_medication_name).toBe("Lisinopril");
  });
});

describe("triggerAnalysis", () => {
  it("posts to the treatment analysis endpoint", async () => {
    const spy = mockFetch({ status: 202, body: { analysis_id: "a1" } });

    const result = await triggerAnalysis("t1");

    const calledUrl = spy.mock.calls[0]?.[0] as string;
    const init = spy.mock.calls[0]?.[1] as RequestInit;
    expect(calledUrl).toMatch(/\/treatments\/t1\/analyze$/);
    expect(init.method).toBe("POST");
    expect(result.analysis_id).toBe("a1");
  });

  it("passes force=true when rerunning an analysis", async () => {
    const spy = mockFetch({ status: 202, body: { analysis_id: "a2" } });

    await triggerAnalysis("t1", { force: true });

    const calledUrl = spy.mock.calls[0]?.[0] as string;
    expect(calledUrl).toContain("/treatments/t1/analyze?force=true");
  });
});

describe("patient check-ins", () => {
  it("lists patient updates for a treatment", async () => {
    const spy = mockFetch({
      status: 200,
      body: {
        items: [
          {
            id: "c1",
            treatment_id: "t1",
            report_type: "not_improving",
            source: "patient",
            message: "Not better yet",
            observed_at: null,
            created_at: "2026-05-18T10:00:00Z",
          },
        ],
      },
    });

    const result = await listPatientCheckIns("t1");

    const calledUrl = spy.mock.calls[0]?.[0] as string;
    expect(calledUrl).toMatch(/\/treatments\/t1\/check-ins$/);
    expect(result.items[0].report_type).toBe("not_improving");
  });

  it("creates a patient update for a treatment", async () => {
    const spy = mockFetch({
      status: 201,
      body: {
        id: "c1",
        treatment_id: "t1",
        report_type: "side_effect",
        source: "pharmacist",
        message: "Dizziness after dose",
        observed_at: null,
        created_at: "2026-05-18T10:00:00Z",
      },
    });

    const result = await createPatientCheckIn("t1", {
      report_type: "side_effect",
      source: "pharmacist",
      message: "Dizziness after dose",
      observed_at: null,
    });

    const calledUrl = spy.mock.calls[0]?.[0] as string;
    const init = spy.mock.calls[0]?.[1] as RequestInit;
    expect(calledUrl).toMatch(/\/treatments\/t1\/check-ins$/);
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toMatchObject({
      report_type: "side_effect",
      source: "pharmacist",
    });
    expect(result.message).toBe("Dizziness after dose");
  });
});

describe("adherence events", () => {
  it("lists adherence events for a treatment", async () => {
    const spy = mockFetch({
      status: 200,
      body: {
        items: [
          {
            id: "e1",
            treatment_id: "t1",
            medication_id: "m1",
            status: "taken",
            source: "patient",
            scheduled_for: "2026-05-18T08:00:00Z",
            occurred_at: "2026-05-18T10:00:00Z",
            note: null,
            created_at: "2026-05-18T10:00:00Z",
          },
        ],
      },
    });

    const result = await listAdherenceEvents("t1");

    const calledUrl = spy.mock.calls[0]?.[0] as string;
    expect(calledUrl).toMatch(/\/treatments\/t1\/adherence-events$/);
    expect(result.items[0].status).toBe("taken");
  });

  it("creates an adherence event for a treatment", async () => {
    const spy = mockFetch({
      status: 201,
      body: {
        id: "e1",
        treatment_id: "t1",
        medication_id: "m1",
        status: "held",
        source: "pharmacist",
        scheduled_for: "2026-05-18T08:00:00Z",
        occurred_at: null,
        note: null,
        created_at: "2026-05-18T10:00:00Z",
      },
    });

    const result = await createAdherenceEvent("t1", {
      medication_id: "m1",
      status: "held",
      source: "pharmacist",
      scheduled_for: "2026-05-18T08:00:00Z",
      occurred_at: null,
      note: null,
    });

    const calledUrl = spy.mock.calls[0]?.[0] as string;
    const init = spy.mock.calls[0]?.[1] as RequestInit;
    expect(calledUrl).toMatch(/\/treatments\/t1\/adherence-events$/);
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toMatchObject({
      medication_id: "m1",
      status: "held",
      source: "pharmacist",
      scheduled_for: "2026-05-18T08:00:00Z",
    });
    expect(result.status).toBe("held");
  });
});

describe("conversation messages", () => {
  it("lists conversation messages for a treatment", async () => {
    const spy = mockFetch({
      status: 200,
      body: {
        items: [
          {
            id: "msg-1",
            treatment_id: "t1",
            direction: "inbound",
            sender_type: "patient",
            channel: "whatsapp",
            status: "received",
            body: "I feel dizzy after taking it.",
            safety_hold_reason: null,
            external_message_id: null,
            created_at: "2026-05-18T10:00:00Z",
          },
        ],
      },
    });

    const result = await listConversationMessages("t1", { limit: 25, offset: 50 });

    const calledUrl = spy.mock.calls[0]?.[0] as string;
    expect(calledUrl).toContain("/treatments/t1/conversation-messages?");
    expect(calledUrl).toContain("limit=25");
    expect(calledUrl).toContain("offset=50");
    expect(result.items[0].body).toBe("I feel dizzy after taking it.");
  });

  it("generates a patient reply draft for a treatment", async () => {
    const spy = mockFetch({
      status: 201,
      body: {
        inbound_message: {
          id: "msg-in",
          treatment_id: "t1",
          direction: "inbound",
          sender_type: "patient",
          channel: "whatsapp",
          status: "received",
          body: "I feel dizzy.",
          safety_hold_reason: null,
          external_message_id: null,
          created_at: "2026-05-18T10:00:00Z",
        },
        assistant_message: {
          id: "msg-out",
          treatment_id: "t1",
          direction: "outbound",
          sender_type: "assistant",
          channel: "whatsapp",
          status: "held_for_review",
          body: "Please stop taking it.",
          safety_hold_reason: "referee",
          external_message_id: null,
          created_at: "2026-05-18T10:00:01Z",
        },
        safety_decision: {
          status: "hold_for_pharmacist",
          message_to_send: null,
          hold_reason: "referee",
          review: {
            input_guard: {
              stage: "input",
              action: "allow",
              categories: [],
              confidence: 0.9,
              rationale: "Allowed.",
            },
            referee: {
              action: "block",
              violation_type: "dosage_change",
              confidence: 0.95,
              rationale: "Draft changed dose.",
            },
            output_guard: {
              stage: "output",
              action: "block",
              categories: ["medical_safety"],
              confidence: 0.9,
              rationale: "Blocked.",
            },
            allowed_to_send: false,
          },
        },
      },
    });

    const result = await draftPatientReply("t1", { patient_message: "I feel dizzy." });

    const calledUrl = spy.mock.calls[0]?.[0] as string;
    const init = spy.mock.calls[0]?.[1] as RequestInit;
    expect(calledUrl).toMatch(/\/treatments\/t1\/patient-reply-drafts$/);
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({ patient_message: "I feel dizzy." });
    expect(result.assistant_message.status).toBe("held_for_review");
  });
});

describe("getAnalysis", () => {
  it("returns null when the backend has no analysis row yet", async () => {
    mockFetch({ status: 204, body: null });

    await expect(getAnalysis("t1")).resolves.toBeNull();
  });

  it("returns the latest analysis row with typed partial-result fields", async () => {
    mockFetch({
      status: 200,
      body: {
        id: "a1",
        treatment_id: "t1",
        status: "failed",
        result: {
          groundings: [],
          ddi_warnings: [],
          schedule: null,
          reasoning: null,
          degraded: true,
          partial_results: true,
          completed_stages: ["ground_medications"],
        },
        error_text: "analysis_failed",
        started_at: "2026-05-12T10:00:00Z",
        completed_at: "2026-05-12T10:01:00Z",
        created_at: "2026-05-12T10:00:00Z",
      },
    });

    const result = await getAnalysis("t1");

    expect(result?.status).toBe("failed");
    expect(result?.result?.partial_results).toBe(true);
    expect(result?.result?.completed_stages).toEqual(["ground_medications"]);
  });
});
