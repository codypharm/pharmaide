import { getJson, patchJson, postJson } from "./client";
import type { ConversationMessageView } from "./treatments";

export type TriageReason =
  | "input_guard"
  | "referee"
  | "output_guard"
  | "adverse_event"
  | "emergency"
  | "side_effect"
  | "dose_change_request"
  | "diagnosis_request"
  | "unclear_message"
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

export type TriageApprovalView = {
  triage_item: TriageItemView;
  approved_message: ConversationMessageView;
};

export type TriageDeliveryView = {
  triage_item: TriageItemView;
  queued_message: ConversationMessageView;
};

export type TriageRejectionView = {
  triage_item: TriageItemView;
  rejected_message: ConversationMessageView;
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

export function approveTriageItem(itemId: string): Promise<TriageApprovalView> {
  return postJson<Record<string, never>, TriageApprovalView>(
    `/triage/items/${itemId}/approve`,
    {},
  );
}

export function rejectTriageItem(itemId: string): Promise<TriageRejectionView> {
  return postJson<Record<string, never>, TriageRejectionView>(
    `/triage/items/${itemId}/reject`,
    {},
  );
}

export function queueTriageItemDelivery(itemId: string): Promise<TriageDeliveryView> {
  return postJson<Record<string, never>, TriageDeliveryView>(
    `/triage/items/${itemId}/queue-delivery`,
    {},
  );
}
