// Typed wrapper around POST /treatments. Mirrors backend
// app/api/schemas.py — see the locked Sprint 2 plan for the contract.

import { postJson } from "./client";

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
