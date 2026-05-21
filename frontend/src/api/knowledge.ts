import { deleteJson, getJson, postMultipart } from "./client";

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

export type ListKnowledgeDocumentsParams = {
  limit?: number;
  offset?: number;
};

export function uploadKnowledgeDocument(file: File): Promise<KnowledgeDocumentCreated> {
  const body = new FormData();
  body.append("file", file);
  return postMultipart<KnowledgeDocumentCreated>("/knowledge/documents", body);
}

export function listKnowledgeDocuments(
  params: ListKnowledgeDocumentsParams,
): Promise<KnowledgeDocumentList> {
  const query = new URLSearchParams();
  if (params.limit !== undefined) query.set("limit", String(params.limit));
  if (params.offset !== undefined) query.set("offset", String(params.offset));
  const qs = query.toString();
  return getJson<KnowledgeDocumentList>(
    qs ? `/knowledge/documents?${qs}` : "/knowledge/documents",
  );
}

export function getKnowledgeDocument(id: string): Promise<KnowledgeDocumentView> {
  return getJson<KnowledgeDocumentView>(`/knowledge/documents/${id}`);
}

export async function deleteKnowledgeDocument(id: string): Promise<void> {
  await deleteJson(`/knowledge/documents/${id}`);
}
