import { AlertCircle, ArrowLeft, Database, FileText, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { ApiError, NotFoundError } from "../api/client";
import {
  PRE_AUTH_KB_SCOPE_ID,
  getKnowledgeDocument,
  type KnowledgeDocumentView,
} from "../api/knowledge";

const KB_SCOPE = { scopeId: PRE_AUTH_KB_SCOPE_ID };

type FetchState =
  | { kind: "loading" }
  | { kind: "ok"; document: KnowledgeDocumentView }
  | { kind: "not-found" }
  | { kind: "error"; requestId: string | null };

export default function KnowledgeDocumentPage() {
  const { id } = useParams<{ id: string }>();
  const [state, setState] = useState<FetchState>({ kind: "loading" });

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    setState({ kind: "loading" });
    getKnowledgeDocument(id, KB_SCOPE)
      .then((document) => {
        if (!cancelled) setState({ kind: "ok", document });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof NotFoundError) {
          setState({ kind: "not-found" });
        } else if (err instanceof ApiError) {
          setState({ kind: "error", requestId: err.requestId });
        } else {
          setState({ kind: "error", requestId: null });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [id]);

  return (
    <div className="h-full overflow-y-auto p-8">
      <div className="flex flex-col gap-6">
        <Header />
        {state.kind === "loading" && <LoadingCard />}
        {state.kind === "not-found" && <NotFoundCard />}
        {state.kind === "error" && <ErrorCard requestId={state.requestId} />}
        {state.kind === "ok" && <DocumentCard document={state.document} />}
      </div>
    </div>
  );
}

function Header() {
  return (
    <div className="flex items-center justify-between gap-4">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-50 text-blue-700">
          <Database size={20} />
        </div>
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-slate-900">Clinical Asset</h2>
          <p className="text-sm text-slate-500">Reference file details for the workspace.</p>
        </div>
      </div>
      <Link
        to="/dashboard/knowledge"
        className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2 font-bold text-slate-700 hover:bg-slate-50"
      >
        <ArrowLeft size={16} />
        Back to assets
      </Link>
    </div>
  );
}

function DocumentCard({ document }: { document: KnowledgeDocumentView }) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white">
      <div className="flex items-start justify-between gap-4 border-b border-slate-200 p-6">
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-slate-200 bg-slate-50 text-slate-500">
            <FileText size={20} />
          </div>
          <div>
            <p className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
              Source
            </p>
            <h3 className="mt-1 text-lg font-bold text-slate-900">{document.title}</h3>
            <p className="mt-1 text-sm text-slate-500">{document.mime}</p>
          </div>
        </div>
        <StatusPill status={document.status} />
      </div>
      <div className="grid gap-4 p-6 sm:grid-cols-2 lg:grid-cols-3">
        <Field label="Availability" value={statusLabel(document.status)} />
        <Field label="Uploaded" value={formatDateTime(document.created_at)} />
        <Field label="Updated" value={formatDateTime(document.updated_at)} />
      </div>
    </section>
  );
}

function LoadingCard() {
  return (
    <div className="flex items-center justify-center gap-3 rounded-xl border border-slate-200 bg-white p-10 text-slate-500">
      <Loader2 size={18} className="animate-spin" />
      <span>Loading clinical asset...</span>
    </div>
  );
}

function NotFoundCard() {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-10 text-center">
      <h3 className="text-lg font-bold text-slate-900">Clinical asset not found</h3>
      <p className="mt-2 text-sm text-slate-500">
        It may have been removed from the workspace.
      </p>
    </div>
  );
}

function ErrorCard({ requestId }: { requestId: string | null }) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-slate-200 bg-white p-6">
      <AlertCircle size={20} className="mt-0.5 text-amber-700" />
      <div>
        <p className="font-bold text-slate-900">Clinical asset is temporarily unavailable.</p>
        <p className="mt-1 text-sm text-slate-500">
          Please retry. Reference ID:{" "}
          <code className="text-slate-700">{requestId ?? "unknown"}</code>
        </p>
      </div>
    </div>
  );
}

function StatusPill({ status }: { status: KnowledgeDocumentView["status"] }) {
  const tone =
    status === "ready"
      ? "border-blue-200 bg-blue-50 text-blue-800"
      : status === "ingesting"
        ? "border-amber-200 bg-amber-50 text-amber-800"
        : "border-red-200 bg-red-50 text-red-800";
  return (
    <span
      className={`inline-flex rounded-full border px-2 py-0.5 text-[11px] font-bold uppercase tracking-wider ${tone}`}
    >
      {statusLabel(status)}
    </span>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="mb-1 text-[11px] font-bold uppercase tracking-wider text-slate-500">
        {label}
      </div>
      <div className="text-sm text-slate-900 tabular-nums">{value}</div>
    </div>
  );
}

function statusLabel(status: KnowledgeDocumentView["status"]): string {
  if (status === "ready") return "File ready";
  if (status === "ingesting") return "Processing";
  if (status === "failed") return "Needs review";
  return "Removed";
}

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}
