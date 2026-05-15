import { getJson, patchJson } from "./client";

export type TriageReason =
  | "input_guard"
  | "referee"
  | "output_guard"
  | "adverse_event"
  | "non_responsive";

export type TriageStatus = "open" | "acknowledged" | "resolved";

export type TriageItemView = {
  id: string;
  treatment_id: string;
  conversation_message_id: string | null;
  reason: TriageReason;
  status: TriageStatus;
  created_at: string;
};

export type TriageItemList = {
  items: TriageItemView[];
};

export type ListTriageItemsParams = {
  limit?: number;
  offset?: number;
};

export function listTriageItems(
  params: ListTriageItemsParams = {},
): Promise<TriageItemList> {
  const query = new URLSearchParams();
  if (params.limit !== undefined) query.set("limit", String(params.limit));
  if (params.offset !== undefined) query.set("offset", String(params.offset));
  const qs = query.toString();
  return getJson<TriageItemList>(qs ? `/triage/items?${qs}` : "/triage/items");
}

export function updateTriageItemStatus(
  itemId: string,
  status: TriageStatus,
): Promise<TriageItemView> {
  return patchJson<{ status: TriageStatus }, TriageItemView>(
    `/triage/items/${itemId}`,
    { status },
  );
}
