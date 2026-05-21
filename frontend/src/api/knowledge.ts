import { deleteJson, getJson, postMultipart } from "./client";

// Kept only while page code still passes an explicit scope object. The backend
// now derives KB scope from the authenticated actor, matching treatment analysis.
export const PRE_AUTH_KB_SCOPE_ID = "anonymous";

export type KnowledgeDocumentStatus = "ingesting" | "ready" | "failed" | "removed";
export type KnowledgeDocumentSourceType = "user_upload" | "dailymed";

export type KnowledgeDocumentCreated = {
  document_id: string;
  status: KnowledgeDocumentStatus;
};

export type KnowledgeDocumentView = {
  id: string;
  source_type: KnowledgeDocumentSourceType;
  title: string;
  mime: string;
  status: KnowledgeDocumentStatus;
  chunk_count: number;
  created_at: string;
  updated_at: string;
};

export type KnowledgeDocumentList = {
  items: KnowledgeDocumentView[];
};

export type KnowledgeScope = {
  scopeId: string;
};

export type ListKnowledgeDocumentsParams = KnowledgeScope & {
  limit?: number;
  offset?: number;
};

export function uploadKnowledgeDocument(
  file: File,
  scope: KnowledgeScope,
): Promise<KnowledgeDocumentCreated> {
  void scope;
  const body = new FormData();
  body.append("file", file);
  return postMultipart<KnowledgeDocumentCreated>("/knowledge/documents", body);
}

export function listKnowledgeDocuments(
  params: ListKnowledgeDocumentsParams,
): Promise<KnowledgeDocumentList> {
  const query = new URLSearchParams();
  void params.scopeId;
  if (params.limit !== undefined) query.set("limit", String(params.limit));
  if (params.offset !== undefined) query.set("offset", String(params.offset));
  const qs = query.toString();
  return getJson<KnowledgeDocumentList>(
    qs ? `/knowledge/documents?${qs}` : "/knowledge/documents",
  );
}

export function getKnowledgeDocument(
  id: string,
  scope: KnowledgeScope,
): Promise<KnowledgeDocumentView> {
  void scope;
  return getJson<KnowledgeDocumentView>(`/knowledge/documents/${id}`);
}

export async function deleteKnowledgeDocument(
  id: string,
  scope: KnowledgeScope,
): Promise<void> {
  void scope;
  await deleteJson(`/knowledge/documents/${id}`);
}
