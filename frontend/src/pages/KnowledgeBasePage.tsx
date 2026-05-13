import {
  AlertCircle,
  Database,
  FileSpreadsheet,
  FileText,
  Loader2,
  RefreshCw,
  Trash2,
  Upload,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { ApiError, NotFoundError } from "../api/client";
import {
  PRE_AUTH_KB_SCOPE_ID,
  deleteKnowledgeDocument,
  listKnowledgeDocuments,
  uploadKnowledgeDocument,
  type KnowledgeDocumentView,
} from "../api/knowledge";

const PAGE_SIZE = 50;
const KB_SCOPE = { scopeId: PRE_AUTH_KB_SCOPE_ID };

type FetchState =
  | { kind: "loading" }
  | { kind: "ok"; items: KnowledgeDocumentView[] }
  | { kind: "error"; error: KnowledgeLoadError };

type KnowledgeLoadError =
  | { kind: "api"; requestId: string | null }
  | { kind: "missing_route"; requestId: string | null }
  | { kind: "network" };

export default function KnowledgeBasePage() {
  const [state, setState] = useState<FetchState>({ kind: "loading" });
  const [busyDocumentId, setBusyDocumentId] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  async function refresh() {
    try {
      const result = await listKnowledgeDocuments({
        ...KB_SCOPE,
        limit: PAGE_SIZE,
        offset: 0,
      });
      setState({ kind: "ok", items: result.items });
    } catch (err) {
      setState({ kind: "error", error: knowledgeLoadError(err) });
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function handleUpload(file: File | undefined) {
    if (!file || isUploading) return;
    setIsUploading(true);
    try {
      await uploadKnowledgeDocument(file, KB_SCOPE);
      await refresh();
      if (fileInputRef.current) fileInputRef.current.value = "";
    } finally {
      setIsUploading(false);
    }
  }

  async function handleDelete(document: KnowledgeDocumentView) {
    if (!window.confirm(`Delete ${document.title}?`)) return;
    setBusyDocumentId(document.id);
    try {
      await deleteKnowledgeDocument(document.id, KB_SCOPE);
      await refresh();
    } finally {
      setBusyDocumentId(null);
    }
  }

  const items = state.kind === "ok" ? state.items : [];

  return (
    <div className="h-full overflow-y-auto p-8">
      <div className="flex flex-col gap-6">
        <Header
          total={items.length}
          isUploading={isUploading}
          onUpload={handleUpload}
          onRefresh={refresh}
          fileInputRef={fileInputRef}
        />

        {state.kind === "loading" && <LoadingCard />}
        {state.kind === "error" && <ErrorCard error={state.error} onRetry={refresh} />}
        {state.kind === "ok" && (
          <>
            <SummaryBand documents={items} />
            {items.length === 0 ? (
              <EmptyCard />
            ) : (
              <DocumentsTable
                items={items}
                busyDocumentId={busyDocumentId}
                onDelete={handleDelete}
              />
            )}
          </>
        )}
      </div>
    </div>
  );
}

function Header({
  total,
  isUploading,
  onUpload,
  onRefresh,
  fileInputRef,
}: {
  total: number;
  isUploading: boolean;
  onUpload: (file: File | undefined) => void;
  onRefresh: () => void;
  fileInputRef: React.RefObject<HTMLInputElement | null>;
}) {
  return (
    <div className="flex items-center justify-between gap-4">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 bg-blue-50 text-blue-700 rounded-xl flex items-center justify-center">
          <Database size={20} />
        </div>
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-slate-900">Clinical Assets</h2>
          <p className="text-sm text-slate-500">
            Upload clinic protocols, formularies, and reference files for grounded analysis.
          </p>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onRefresh}
          className="inline-flex items-center gap-2 px-4 py-2 bg-white border border-slate-200 text-slate-700 rounded-xl font-bold hover:bg-slate-50 cursor-pointer"
        >
          <RefreshCw size={16} />
          Refresh
        </button>
        <label className="inline-flex items-center gap-2 px-4 py-2 bg-slate-900 text-white rounded-xl font-bold hover:bg-slate-800 cursor-pointer">
          {isUploading ? <Loader2 size={16} className="animate-spin" /> : <Upload size={16} />}
          {isUploading ? "Uploading" : "Upload"}
          <input
            ref={fileInputRef}
            aria-label="Upload clinical asset"
            type="file"
            accept=".pdf,.txt,.csv,application/pdf,text/plain,text/csv"
            className="sr-only"
            disabled={isUploading}
            onChange={(event) => onUpload(event.target.files?.[0])}
          />
        </label>
        <span className="text-xs font-bold uppercase tracking-wider text-slate-500">
          {total} assets
        </span>
      </div>
    </div>
  );
}

function SummaryBand({ documents }: { documents: KnowledgeDocumentView[] }) {
  const ready = documents.filter((document) => document.status === "ready").length;
  const ingesting = documents.filter((document) => document.status === "ingesting").length;
  const failed = documents.filter((document) => document.status === "failed").length;

  return (
    <section className="grid grid-cols-3 gap-4">
      <Metric label="Ready" value={ready} tone="text-blue-700" />
      <Metric label="Ingesting" value={ingesting} tone="text-amber-700" />
      <Metric label="Failed" value={failed} tone="text-red-700" />
    </section>
  );
}

function Metric({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5">
      <p className="text-[11px] font-bold uppercase tracking-wider text-slate-500">{label}</p>
      <p className={`mt-2 text-3xl font-bold tabular-nums ${tone}`}>{value}</p>
    </div>
  );
}

function DocumentsTable({
  items,
  busyDocumentId,
  onDelete,
}: {
  items: KnowledgeDocumentView[];
  busyDocumentId: string | null;
  onDelete: (document: KnowledgeDocumentView) => void;
}) {
  return (
    <section className="bg-white border border-slate-200 rounded-xl overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-slate-50">
            <tr className="text-[11px] font-bold uppercase tracking-wider text-slate-500 border-b border-slate-200">
              <th className="text-left px-6 py-3">Source</th>
              <th className="text-left px-6 py-3">Status</th>
              <th className="text-left px-6 py-3">Chunks</th>
              <th className="text-left px-6 py-3">Updated</th>
              <th className="px-6 py-3 w-16"></th>
            </tr>
          </thead>
          <tbody>
            {items.map((document, index) => (
              <tr
                key={document.id}
                className={`border-b border-slate-100 last:border-b-0 ${
                  index % 2 === 1 ? "bg-slate-50/50" : ""
                } hover:bg-blue-50/50`}
              >
                <td className="px-6 py-4">
                  <div className="flex items-center gap-3">
                    <div className="w-9 h-9 bg-slate-50 border border-slate-200 rounded-lg flex items-center justify-center text-slate-500">
                      {document.mime.includes("csv") ? (
                        <FileSpreadsheet size={18} />
                      ) : (
                        <FileText size={18} />
                      )}
                    </div>
                    <div>
                      <p className="font-bold text-slate-900">{document.title}</p>
                      <p className="text-xs text-slate-500">{document.mime}</p>
                    </div>
                  </div>
                </td>
                <td className="px-6 py-4">
                  <StatusPill status={document.status} />
                </td>
                <td className="px-6 py-4 text-slate-700 tabular-nums">
                  {document.chunk_count} chunks
                </td>
                <td className="px-6 py-4 text-slate-700 tabular-nums">
                  {formatDateTime(document.updated_at)}
                </td>
                <td className="px-6 py-4 text-right">
                  <button
                    type="button"
                    aria-label={`Delete ${document.title}`}
                    disabled={busyDocumentId === document.id}
                    onClick={() => onDelete(document)}
                    className="inline-flex items-center justify-center w-8 h-8 rounded-lg text-slate-400 hover:text-red-700 hover:bg-red-50 disabled:opacity-50 cursor-pointer"
                  >
                    {busyDocumentId === document.id ? (
                      <Loader2 size={16} className="animate-spin" />
                    ) : (
                      <Trash2 size={16} />
                    )}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function StatusPill({ status }: { status: KnowledgeDocumentView["status"] }) {
  const tone =
    status === "ready"
      ? "bg-blue-50 text-blue-800 border-blue-200"
      : status === "ingesting"
        ? "bg-amber-50 text-amber-800 border-amber-200"
        : "bg-red-50 text-red-800 border-red-200";
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full border text-[11px] font-bold uppercase tracking-wider ${tone}`}
    >
      {statusLabel(status)}
    </span>
  );
}

function LoadingCard() {
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-10 flex items-center justify-center gap-3 text-slate-500">
      <Loader2 size={18} className="animate-spin" />
      <span>Loading clinical assets...</span>
    </div>
  );
}

function EmptyCard() {
  return (
    <section className="bg-white border border-slate-200 rounded-xl p-8">
      <div className="flex items-start gap-4">
        <div className="w-12 h-12 rounded-xl bg-blue-50 text-blue-700 flex items-center justify-center shrink-0">
          <Upload size={24} />
        </div>
        <div>
          <p className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
            No data available
          </p>
          <h3 className="text-xl font-bold text-slate-900 mt-2">No clinical assets uploaded</h3>
          <p className="text-sm text-slate-500 mt-2 max-w-2xl">
            Upload clinic protocols, formularies, or reference files for this workspace.
          </p>
          <div className="mt-5 flex flex-wrap gap-2">
            <FileTypeChip label="PDF" />
            <FileTypeChip label="TXT" />
            <FileTypeChip label="CSV" />
          </div>
        </div>
      </div>
    </section>
  );
}

function FileTypeChip({ label }: { label: string }) {
  return (
    <span className="inline-flex items-center rounded-md border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-bold text-slate-700">
      {label}
    </span>
  );
}

function ErrorCard({
  error,
  onRetry,
}: {
  error: KnowledgeLoadError;
  onRetry: () => void;
}) {
  const copy = errorCopy(error);
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-6 flex items-start justify-between gap-4">
      <div className="flex items-start gap-3">
        <AlertCircle size={20} className="text-amber-700 mt-0.5" />
        <div>
          <p className="font-bold text-slate-900">{copy.title}</p>
          <p className="text-sm text-slate-500 mt-1">
            {copy.detail}
            {copy.requestId && (
              <>
                {" "}
                Reference ID: <code className="text-slate-700">{copy.requestId}</code>
              </>
            )}
          </p>
        </div>
      </div>
      <button
        type="button"
        onClick={onRetry}
        className="inline-flex items-center gap-2 px-4 py-2 bg-white border border-slate-200 text-slate-700 rounded-xl font-bold hover:bg-slate-50 cursor-pointer"
      >
        <RefreshCw size={16} />
        Retry
      </button>
    </div>
  );
}

function knowledgeLoadError(err: unknown): KnowledgeLoadError {
  if (err instanceof NotFoundError) {
    return { kind: "missing_route", requestId: err.requestId };
  }
  if (err instanceof ApiError) {
    return { kind: "api", requestId: err.requestId };
  }
  return { kind: "network" };
}

function errorCopy(error: KnowledgeLoadError): {
  title: string;
  detail: string;
  requestId: string | null;
} {
  if (error.kind === "missing_route") {
    return {
      title: "Clinical assets are being prepared.",
      detail: "Try again shortly, or continue reviewing treatments without uploaded reference material.",
      requestId: error.requestId,
    };
  }
  if (error.kind === "network") {
    return {
      title: "Clinical assets are temporarily unavailable.",
      detail: "Try again shortly, or continue without uploaded reference material.",
      requestId: null,
    };
  }
  return {
    title: "Clinical assets are temporarily unavailable.",
    detail: "Try again shortly.",
    requestId: error.requestId,
  };
}

function statusLabel(status: KnowledgeDocumentView["status"]): string {
  if (status === "ready") return "Ready";
  if (status === "ingesting") return "Ingesting";
  if (status === "failed") return "Failed";
  return "Removed";
}

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}
