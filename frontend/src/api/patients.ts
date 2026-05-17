import { getJson } from "./client";
import type { PatientView } from "./treatments";

export type PatientList = {
  items: PatientView[];
};

export type PatientSearchParams = {
  query: string;
  limit?: number;
  offset?: number;
};

export function searchPatients(params: PatientSearchParams): Promise<PatientList> {
  const query = new URLSearchParams();
  query.set("query", params.query);
  if (params.limit !== undefined) query.set("limit", String(params.limit));
  if (params.offset !== undefined) query.set("offset", String(params.offset));
  return getJson<PatientList>(`/patients?${query.toString()}`);
}
