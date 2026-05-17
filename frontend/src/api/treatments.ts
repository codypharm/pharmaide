// Typed wrapper around POST /treatments. Mirrors backend
// app/api/schemas.py — see the locked Sprint 2 plan for the contract.

import { getJson, postJson } from "./client";

export type IngestionMethod = "structured" | "manual" | "vision";

export type PatientCreate = {
  name: string;
  dob: string; // YYYY-MM-DD
  mrn: string;
  phone: string; // E.164 form, e.g. +18005551212
  allergies: string[];
};

export type MedicationCreate = {
  name: string;
  dosage: string;
  frequency: string;
  duration: string;
  objective: string | null;
};

export type TreatmentCreatePayload = {
  patient: PatientCreate;
  treatment: {
    clinical_objective: string | null;
    treatment_start_at: string | null;
  };
  medications: MedicationCreate[];
  ingestion_method: IngestionMethod;
};

export type CreateTreatmentResponse = {
  treatment_id: string;
  patient_id: string;
  analysis_id: string | null;
};

export function createTreatment(
  payload: TreatmentCreatePayload,
): Promise<CreateTreatmentResponse> {
  return postJson<TreatmentCreatePayload, CreateTreatmentResponse>("/treatments", payload);
}

// GET /treatments/:id — mirrors backend TreatmentDetail.

export type PatientView = {
  id: string;
  name: string;
  dob: string;
  mrn: string;
  phone: string;
  allergies: string[];
};

export type TreatmentView = {
  id: string;
  patient_id: string;
  status: string;
  chat_response_mode: "ai_active" | "pharmacist_takeover";
  automation_mode: "active" | "paused";
  clinical_objective: string | null;
  treatment_start_at: string | null;
  created_at: string; // ISO 8601
};

export type MedicationView = {
  id: string;
  name: string;
  dosage: string;
  frequency: string;
  duration: string;
  objective: string | null;
  ordinal: number;
};

export type TreatmentDetail = {
  patient: PatientView;
  treatment: TreatmentView;
  medications: MedicationView[];
};

export function getTreatment(id: string): Promise<TreatmentDetail> {
  return getJson<TreatmentDetail>(`/treatments/${id}`);
}

// GET /treatments/:id/completion-report — PHI-minimized end-of-course counts.

export type CompletionReportCounts = {
  total_count: number;
  by_status: Record<string, number>;
};

export type PatientUpdateReportCounts = {
  total_count: number;
  by_report_type: Record<string, number>;
};

export type TriageReportCounts = {
  total_count: number;
  by_status: Record<string, number>;
  by_reason: Record<string, number>;
};

export type CourseCompletionReport = {
  treatment_id: string;
  patient_id: string;
  status: string;
  treatment_start_at: string | null;
  created_at: string;
  medication_count: number;
  adherence: CompletionReportCounts;
  patient_updates: PatientUpdateReportCounts;
  triage: TriageReportCounts;
};

export function getCompletionReport(treatmentId: string): Promise<CourseCompletionReport> {
  return getJson<CourseCompletionReport>(`/treatments/${treatmentId}/completion-report`);
}

// POST/GET /treatments/:id/check-ins — patient-reported clinical status.

export type PatientCheckInReportType =
  | "not_improving"
  | "side_effect"
  | "feeling_better"
  | "general_update"
  | "missed_dose";

export type PatientCheckInSource = "patient" | "pharmacist" | "system";

export type PatientCheckInCreate = {
  report_type: PatientCheckInReportType;
  source: PatientCheckInSource;
  message: string;
  observed_at: string | null;
};

export type PatientCheckInView = PatientCheckInCreate & {
  id: string;
  treatment_id: string;
  created_at: string;
};

export type PatientCheckInList = {
  items: PatientCheckInView[];
};

export function createPatientCheckIn(
  treatmentId: string,
  payload: PatientCheckInCreate,
): Promise<PatientCheckInView> {
  return postJson<PatientCheckInCreate, PatientCheckInView>(
    `/treatments/${treatmentId}/check-ins`,
    payload,
  );
}

export function listPatientCheckIns(treatmentId: string): Promise<PatientCheckInList> {
  return getJson<PatientCheckInList>(`/treatments/${treatmentId}/check-ins`);
}

// POST/GET /treatments/:id/adherence-events — structured dose/reminder state.

export type AdherenceEventStatus = "taken" | "missed" | "held" | "skipped";
export type AdherenceEventSource = "patient" | "pharmacist" | "system";

export type AdherenceEventCreate = {
  medication_id: string;
  status: AdherenceEventStatus;
  source: AdherenceEventSource;
  scheduled_for: string | null;
  occurred_at: string | null;
  note: string | null;
};

export type AdherenceEventView = AdherenceEventCreate & {
  id: string;
  treatment_id: string;
  created_at: string;
};

export type AdherenceEventList = {
  items: AdherenceEventView[];
};

export function createAdherenceEvent(
  treatmentId: string,
  payload: AdherenceEventCreate,
): Promise<AdherenceEventView> {
  return postJson<AdherenceEventCreate, AdherenceEventView>(
    `/treatments/${treatmentId}/adherence-events`,
    payload,
  );
}

export function listAdherenceEvents(treatmentId: string): Promise<AdherenceEventList> {
  return getJson<AdherenceEventList>(`/treatments/${treatmentId}/adherence-events`);
}

// GET /treatments/:id/conversation-messages — treatment chat history.

export type ConversationMessageDirection = "inbound" | "outbound";
export type ConversationMessageSender = "patient" | "assistant" | "pharmacist" | "system";
export type ConversationMessageChannel = "whatsapp" | "dashboard" | "system";
export type ConversationMessageStatus =
  | "received"
  | "draft_ready"
  | "held_for_review"
  | "approved"
  | "rejected"
  | "queued"
  | "sent"
  | "failed";

export type ConversationMessageView = {
  id: string;
  treatment_id: string;
  direction: ConversationMessageDirection;
  sender_type: ConversationMessageSender;
  channel: ConversationMessageChannel;
  status: ConversationMessageStatus;
  body: string;
  safety_hold_reason: string | null;
  external_message_id: string | null;
  created_at: string;
};

export type ConversationMessageList = {
  items: ConversationMessageView[];
};

export type PatientDraftSafetyStatus = "send" | "hold_for_pharmacist";
export type PatientDraftHoldReason =
  | "input_guard"
  | "referee"
  | "output_guard"
  | "draft_requires_review";

export type PatientDraftSafetyDecision = {
  status: PatientDraftSafetyStatus;
  message_to_send: string | null;
  hold_reason: PatientDraftHoldReason | null;
  review?: unknown;
};

export type ConversationTurnView = {
  inbound_message: ConversationMessageView;
  assistant_message: ConversationMessageView;
  safety_decision: PatientDraftSafetyDecision;
};

export type ListConversationMessagesParams = {
  limit?: number;
  offset?: number;
};

export type PatientReplyDraftCreate = {
  patient_message: string;
};

export type PharmacistMessageCreate = {
  message: string;
};

export type TreatmentChatResponseModeUpdate = {
  chat_response_mode: TreatmentView["chat_response_mode"];
};

export type TreatmentClinicalObjectiveUpdate = {
  clinical_objective: string | null;
};

export function listConversationMessages(
  treatmentId: string,
  params: ListConversationMessagesParams = {},
): Promise<ConversationMessageList> {
  const query = new URLSearchParams();
  if (params.limit !== undefined) query.set("limit", String(params.limit));
  if (params.offset !== undefined) query.set("offset", String(params.offset));
  const qs = query.toString();
  return getJson<ConversationMessageList>(
    `/treatments/${treatmentId}/conversation-messages${qs ? `?${qs}` : ""}`,
  );
}

export function draftPatientReply(
  treatmentId: string,
  payload: PatientReplyDraftCreate,
): Promise<ConversationTurnView> {
  return postJson<PatientReplyDraftCreate, ConversationTurnView>(
    `/treatments/${treatmentId}/patient-reply-drafts`,
    payload,
  );
}

export function sendPharmacistMessage(
  treatmentId: string,
  payload: PharmacistMessageCreate,
): Promise<ConversationMessageView> {
  return postJson<PharmacistMessageCreate, ConversationMessageView>(
    `/treatments/${treatmentId}/pharmacist-messages`,
    payload,
  );
}

export function retryConversationMessageDelivery(
  treatmentId: string,
  messageId: string,
): Promise<ConversationMessageView> {
  return postJson<undefined, ConversationMessageView>(
    `/treatments/${treatmentId}/conversation-messages/${messageId}/retry-delivery`,
    undefined,
  );
}

export function updateTreatmentChatResponseMode(
  treatmentId: string,
  payload: TreatmentChatResponseModeUpdate,
): Promise<TreatmentView> {
  return postJson<TreatmentChatResponseModeUpdate, TreatmentView>(
    `/treatments/${treatmentId}/chat-response-mode`,
    payload,
  );
}

export function updateTreatmentClinicalObjective(
  treatmentId: string,
  payload: TreatmentClinicalObjectiveUpdate,
): Promise<TreatmentView> {
  return postJson<TreatmentClinicalObjectiveUpdate, TreatmentView>(
    `/treatments/${treatmentId}/clinical-objective`,
    payload,
  );
}

export function startTreatmentCycle(treatmentId: string): Promise<TreatmentView> {
  return postJson<undefined, TreatmentView>(
    `/treatments/${treatmentId}/start-cycle`,
    undefined,
  );
}

// GET /treatments — paginated list. Mirrors backend TreatmentList.

export type TreatmentListItem = {
  patient: PatientView;
  treatment: TreatmentView;
  medication_count: number;
  first_medication_name: string | null;
};

export type TreatmentList = {
  items: TreatmentListItem[];
};

export type ListTreatmentsParams = {
  limit?: number;
  offset?: number;
};

export function listTreatments(params: ListTreatmentsParams = {}): Promise<TreatmentList> {
  const query = new URLSearchParams();
  if (params.limit !== undefined) query.set("limit", String(params.limit));
  if (params.offset !== undefined) query.set("offset", String(params.offset));
  const qs = query.toString();
  return getJson<TreatmentList>(qs ? `/treatments?${qs}` : "/treatments");
}

// POST/GET /treatments/:id/analysis — mirrors backend TreatmentAnalysisView.

export type AnalysisStatus = "pending" | "running" | "completed" | "failed" | "superseded";

export type MedicationGrounding = {
  medication_id: string;
  medication_name: string;
  rxcui: string | null;
  normalized_name: string | null;
  confidence: number;
};

export type DDIWarning = {
  medication_ids: string[];
  severity: "minor" | "moderate" | "major";
  description: string;
  source: string;
};

export type ReminderSlot = {
  medication_id: string;
  offset_from_start: string;
  human_label: string;
};

export type Schedule = {
  reminders: ReminderSlot[];
};

export type ClinicalReasoning = {
  summary: string;
  red_flags: string[];
  confidence: number;
};

export type ClinicalSafetyReview = {
  source_type: "model_review";
  possible_interactions: string[];
  monitoring_concerns: string[];
  counseling_points: string[];
  missing_information: string[];
  confidence: number;
  requires_pharmacist_review: true;
};

export type KBCitation = {
  chunk_id: string;
  document_id: string;
  source_type: "user_upload" | "dailymed";
  document_title: string;
  source_uri: string;
  text: string;
  score: number;
};

export type AnalysisResult = {
  groundings: MedicationGrounding[];
  ddi_warnings: DDIWarning[];
  schedule: Schedule | null;
  kb_citations: KBCitation[];
  clinical_safety_review?: ClinicalSafetyReview | null;
  reasoning: ClinicalReasoning | null;
  degraded: boolean;
  partial_results: boolean;
  completed_stages: string[];
};

export type TreatmentAnalysisSnapshot = {
  id: string;
  treatment_id: string;
  status: AnalysisStatus;
  result: AnalysisResult | null;
  error_text: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
};

export type TreatmentAnalysisRow = TreatmentAnalysisSnapshot & {
  last_completed?: TreatmentAnalysisSnapshot | null;
};

export type AnalyzeTreatmentResponse = {
  analysis_id: string;
};

export type TriggerAnalysisOptions = {
  force?: boolean;
};

export function triggerAnalysis(
  id: string,
  options: TriggerAnalysisOptions = {},
): Promise<AnalyzeTreatmentResponse> {
  const qs = options.force ? "?force=true" : "";
  return postJson<Record<string, never>, AnalyzeTreatmentResponse>(
    `/treatments/${id}/analyze${qs}`,
    {},
  );
}

export function getAnalysis(id: string): Promise<TreatmentAnalysisRow | null> {
  return getJson<TreatmentAnalysisRow | null>(`/treatments/${id}/analysis`);
}
