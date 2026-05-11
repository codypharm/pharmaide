// Typed wrapper around POST /treatments. Mirrors backend
// app/api/schemas.py — see the locked Sprint 2 plan for the contract.

import { getJson, postJson } from "./client";

export type IngestionMethod = "structured" | "manual" | "vision";

export type PatientCreate = {
  name: string;
  dob: string; // YYYY-MM-DD
  mrn: string;
  phone: string; // E.164 form, e.g. +18005551212
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
  treatment: { clinical_objective: string | null };
  medications: MedicationCreate[];
  ingestion_method: IngestionMethod;
};

export type CreateTreatmentResponse = {
  treatment_id: string;
  patient_id: string;
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
};

export type TreatmentView = {
  id: string;
  patient_id: string;
  status: string;
  clinical_objective: string | null;
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
