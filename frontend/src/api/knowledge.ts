import { deleteJson, getJson, postMultipart } from "./client";

export type KnowledgeDocumentStatus = "ingesting" | "ready" | "failed" | "removed";

export type KnowledgeDocumentCreated = {
  document_id: string;
  status: KnowledgeDocumentStatus;
};

export type KnowledgeDocumentView = {
  id: string;
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
  const body = new FormData();
  body.append("file", file);
  return postMultipart<KnowledgeDocumentCreated>("/knowledge/documents", body, {
    headers: scopeHeaders(scope),
  });
}

export function listKnowledgeDocuments(
  params: ListKnowledgeDocumentsParams,
): Promise<KnowledgeDocumentList> {
  const query = new URLSearchParams();
  if (params.limit !== undefined) query.set("limit", String(params.limit));
  if (params.offset !== undefined) query.set("offset", String(params.offset));
  const qs = query.toString();
  return getJson<KnowledgeDocumentList>(qs ? `/knowledge/documents?${qs}` : "/knowledge/documents", {
    headers: scopeHeaders(params),
  });
}

export function getKnowledgeDocument(
  id: string,
  scope: KnowledgeScope,
): Promise<KnowledgeDocumentView> {
  return getJson<KnowledgeDocumentView>(`/knowledge/documents/${id}`, {
    headers: scopeHeaders(scope),
  });
}

export async function deleteKnowledgeDocument(
  id: string,
  scope: KnowledgeScope,
): Promise<void> {
  await deleteJson(`/knowledge/documents/${id}`, {
    headers: scopeHeaders(scope),
  });
}

function scopeHeaders(scope: KnowledgeScope): Record<string, string> {
  return { "X-Pharmaide-User-Id": scope.scopeId };
}
