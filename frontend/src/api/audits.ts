import { getJson } from "./client";

export type AuditLogEntryView = {
  id: string;
  actor_id: string | null;
  event_type: string;
  resource_type: string;
  resource_id: string;
  payload: Record<string, unknown>;
  created_at: string;
};

export type AuditLogEntryList = {
  items: AuditLogEntryView[];
};

export type ListAuditLogEntriesParams = {
  limit?: number;
  offset?: number;
};

export function listAuditLogEntries(
  params: ListAuditLogEntriesParams = {},
): Promise<AuditLogEntryList> {
  const query = new URLSearchParams();
  if (params.limit !== undefined) query.set("limit", String(params.limit));
  if (params.offset !== undefined) query.set("offset", String(params.offset));
  const qs = query.toString();
  return getJson<AuditLogEntryList>(qs ? `/audits?${qs}` : "/audits");
}
