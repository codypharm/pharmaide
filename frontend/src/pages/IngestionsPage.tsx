import { useEffect, useState } from "react";
import { Link, useNavigate, useOutletContext } from "react-router-dom";
import {
  AlertCircle,
  CheckCircle2,
  ChevronRight,
  ClipboardList,
  FilePlus2,
  Loader2,
  Plus,
} from "lucide-react";

import { ApiError } from "../api/client";
import { listTreatments, type TreatmentListItem } from "../api/treatments";

type OutletContext = {
  isPrivacyMode: boolean;
};

const PAGE_SIZE = 50;

type FetchState =
  | { kind: "loading" }
  | { kind: "ok"; items: TreatmentListItem[]; hasMore: boolean }
  | { kind: "error"; requestId: string | null };

function formatCreatedAt(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export default function IngestionsPage() {
  const { isPrivacyMode } = useOutletContext<OutletContext>();
  const [state, setState] = useState<FetchState>({ kind: "loading" });
  const [loadingMore, setLoadingMore] = useState(false);

  useEffect(() => {
    let cancelled = false;
    listTreatments({ limit: PAGE_SIZE, offset: 0 })
      .then((res) => {
        if (cancelled) return;
        setState({ kind: "ok", items: res.items, hasMore: res.items.length === PAGE_SIZE });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setState({
          kind: "error",
          requestId: err instanceof ApiError ? err.requestId : null,
        });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function loadMore() {
    if (state.kind !== "ok" || loadingMore) return;
    setLoadingMore(true);
    try {
      const next = await listTreatments({ limit: PAGE_SIZE, offset: state.items.length });
      setState({
        kind: "ok",
        items: [...state.items, ...next.items],
        hasMore: next.items.length === PAGE_SIZE,
      });
    } finally {
      setLoadingMore(false);
    }
  }

  return (
    <div className="h-full overflow-y-auto p-8">
      <div className="flex flex-col gap-6">
        <Header />
        {state.kind === "loading" && <LoadingCard />}
        {state.kind === "error" && <ErrorCard requestId={state.requestId} />}
        {state.kind === "ok" && state.items.length === 0 && <EmptyCard />}
        {state.kind === "ok" && state.items.length > 0 && (
          <>
            <IngestionsTable items={state.items} isPrivacyMode={isPrivacyMode} />
            {state.hasMore && (
              <div className="flex justify-center">
                <button
                  type="button"
                  onClick={loadMore}
                  disabled={loadingMore}
                  className="px-5 py-2 bg-white border border-slate-200 text-slate-700 rounded-xl font-bold hover:bg-slate-50 transition-colors shadow-sm flex items-center gap-2 disabled:opacity-50"
                >
                  {loadingMore && <Loader2 size={16} className="animate-spin" />}
                  Load more
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function Header() {
  return (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 bg-[#F0EFFF] text-[#5548E8] rounded-xl flex items-center justify-center shadow-sm">
          <ClipboardList size={20} />
        </div>
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-slate-900">Treatments</h2>
          <p className="text-sm text-slate-500">All treatments you have registered, newest first.</p>
        </div>
      </div>
      <Link
        to="/dashboard/new-treatment"
        className="px-4 py-2 bg-white border border-slate-200 text-slate-600 rounded-xl font-bold hover:bg-slate-50 transition-colors shadow-sm flex items-center gap-2"
      >
        <Plus size={16} />
        New Treatment
      </Link>
    </div>
  );
}

function LoadingCard() {
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-10 flex items-center justify-center gap-3 text-slate-500">
      <Loader2 size={18} className="animate-spin" />
      <span>Loading ingestions…</span>
    </div>
  );
}

function EmptyCard() {
  return (
    <section className="bg-white border border-slate-200 rounded-xl overflow-hidden">
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px]">
        <div className="p-8 flex items-start gap-4">
          <div className="w-12 h-12 rounded-xl bg-[#F0EFFF] text-[#5548E8] flex items-center justify-center shrink-0">
            <FilePlus2 size={24} />
          </div>
          <div>
            <p className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
              No data available
            </p>
            <h3 className="text-xl font-bold text-slate-900 mt-2">No treatments registered</h3>
            <p className="text-sm text-slate-500 mt-2 max-w-2xl">
              Create the first treatment when a prescription is ready for pharmacist review.
            </p>
            <Link
              to="/dashboard/new-treatment"
              className="mt-5 inline-flex items-center gap-2 px-4 py-2 bg-slate-900 text-white rounded-xl font-bold hover:bg-slate-800 cursor-pointer"
            >
              <Plus size={16} />
              New Treatment
            </Link>
          </div>
        </div>
        <div className="border-t lg:border-t-0 lg:border-l border-slate-200 bg-slate-50/60 p-6">
          <p className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
            Once added
          </p>
          <div className="mt-4 space-y-3 text-sm text-slate-600">
            <EmptyStatePoint text="Patient and prescription details appear here." />
            <EmptyStatePoint text="Reasoning can be started from the treatment detail page." />
            <EmptyStatePoint text="Privacy mode masks patient identifiers in this list." />
          </div>
        </div>
      </div>
    </section>
  );
}

function EmptyStatePoint({ text }: { text: string }) {
  return (
    <div className="flex items-start gap-2">
      <CheckCircle2 size={16} className="text-[#5548E8] mt-0.5 shrink-0" />
      <span>{text}</span>
    </div>
  );
}

function ErrorCard({ requestId }: { requestId: string | null }) {
  return (
    <div className="bg-white border border-red-200 rounded-xl p-6 flex items-start gap-3">
      <AlertCircle size={20} className="text-red-700 mt-0.5" />
      <div>
        <p className="font-bold text-slate-900">Could not load ingestions.</p>
        <p className="text-sm text-slate-500 mt-1">
          Please retry. Reference ID: <code className="text-slate-700">{requestId ?? "unknown"}</code>
        </p>
      </div>
    </div>
  );
}

function IngestionsTable({
  items,
  isPrivacyMode,
}: {
  items: TreatmentListItem[];
  isPrivacyMode: boolean;
}) {
  const navigate = useNavigate();
  const phiClass = isPrivacyMode ? "blur-sm select-none" : "";
  const openTreatment = (treatmentId: string) => {
    navigate(`/dashboard/treatments/${treatmentId}`);
  };

  return (
    <section className="bg-white border border-slate-200 rounded-xl overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-slate-50">
            <tr className="text-[11px] font-bold uppercase tracking-wider text-slate-500 border-b border-slate-200">
              <th className="text-left px-6 py-3">Created</th>
              <th className="text-left px-6 py-3">Patient</th>
              <th className="text-left px-6 py-3">MRN</th>
              <th className="text-left px-6 py-3">Status</th>
              <th className="text-left px-6 py-3">Medications</th>
              <th className="px-6 py-3 w-12"></th>
            </tr>
          </thead>
          <tbody>
            {items.map((row, i) => (
              <tr
                key={row.treatment.id}
                role="link"
                tabIndex={0}
                aria-label={`View treatment for ${row.patient.name}`}
                onClick={() => openTreatment(row.treatment.id)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    openTreatment(row.treatment.id);
                  }
                }}
                className={`border-b border-slate-100 last:border-b-0 cursor-pointer focus:outline-none focus:bg-[#F0EFFF]/70 ${i % 2 === 1 ? "bg-slate-50/50" : ""} hover:bg-[#F0EFFF]/60`}
              >
                <td className="px-6 py-3 text-slate-700 tabular-nums">
                  {formatCreatedAt(row.treatment.created_at)}
                </td>
                <td className={`px-6 py-3 text-slate-900 font-medium ${phiClass}`}>
                  {row.patient.name}
                </td>
                <td className={`px-6 py-3 text-slate-700 tabular-nums ${phiClass}`}>
                  {row.patient.mrn}
                </td>
                <td className="px-6 py-3">
                  <StatusPill status={row.treatment.status} />
                </td>
                <td className="px-6 py-3 text-slate-700">
                  <span className="tabular-nums">{row.medication_count}</span>
                  {row.first_medication_name && (
                    <span className="text-slate-500"> · {row.first_medication_name}</span>
                  )}
                </td>
                <td className="px-6 py-3 text-right">
                  <Link
                    to={`/dashboard/treatments/${row.treatment.id}`}
                    onClick={(event) => event.stopPropagation()}
                    className="inline-flex items-center justify-center w-8 h-8 rounded-lg text-slate-400 hover:text-slate-900 hover:bg-slate-100"
                    aria-label={`View treatment ${row.treatment.id}`}
                  >
                    <ChevronRight size={16} />
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function StatusPill({ status }: { status: string }) {
  // Status palette stays light until Sprint 3 introduces lifecycle changes.
  const tone =
    status === "pending"
      ? "bg-amber-50 text-amber-800 border-amber-200"
      : status === "active"
        ? "bg-[#F0EFFF] text-[#463AD4] border-[#D9D5FB]"
        : status === "completed"
          ? "bg-emerald-50 text-emerald-800 border-emerald-200"
          : "bg-slate-50 text-slate-700 border-slate-200";
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full border text-[11px] font-bold uppercase tracking-wider ${tone}`}>
      {status}
    </span>
  );
}
