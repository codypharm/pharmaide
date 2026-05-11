import { useEffect, useState } from "react";
import { Link, useOutletContext, useParams } from "react-router-dom";
import {
  ArrowLeft,
  ClipboardList,
  Pill,
  User,
  Loader2,
  AlertCircle,
} from "lucide-react";

import { ApiError, NotFoundError } from "../api/client";
import { getTreatment, type TreatmentDetail } from "../api/treatments";

type OutletContext = {
  isPrivacyMode: boolean;
};

type FetchState =
  | { kind: "loading" }
  | { kind: "ok"; data: TreatmentDetail }
  | { kind: "not-found" }
  | { kind: "error"; requestId: string | null };

function formatCreatedAt(iso: string): string {
  // Locale-aware, readable in a clinical context. Tabular numerals come
  // from the global CSS — see DESIGN.md "tabular figures for timestamps".
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

export default function TreatmentDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { isPrivacyMode } = useOutletContext<OutletContext>();
  const [state, setState] = useState<FetchState>({ kind: "loading" });

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    setState({ kind: "loading" });
    getTreatment(id)
      .then((data) => {
        if (!cancelled) setState({ kind: "ok", data });
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
        {state.kind === "ok" && (
          <>
            <PatientCard data={state.data} isPrivacyMode={isPrivacyMode} />
            <TreatmentCard data={state.data} />
            <MedicationsCard data={state.data} />
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
        <div className="w-10 h-10 bg-blue-50 text-blue-600 rounded-xl flex items-center justify-center shadow-sm">
          <ClipboardList size={20} />
        </div>
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-slate-900">
            Treatment Detail
          </h2>
          <p className="text-sm text-slate-500">
            Read-only view of the ingested prescription.
          </p>
        </div>
      </div>
      <Link
        to="/dashboard/new-treatment"
        className="px-4 py-2 bg-white border border-slate-200 text-slate-600 rounded-xl font-bold hover:bg-slate-50 transition-colors shadow-sm flex items-center gap-2"
      >
        <ArrowLeft size={16} />
        Back
      </Link>
    </div>
  );
}

function LoadingCard() {
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-10 flex items-center justify-center gap-3 text-slate-500">
      <Loader2 size={18} className="animate-spin" />
      <span>Loading treatment…</span>
    </div>
  );
}

function NotFoundCard() {
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-10 text-center">
      <h3 className="text-lg font-bold text-slate-900 mb-2">
        Treatment not found
      </h3>
      <p className="text-sm text-slate-500 mb-4">
        This treatment may have been removed or never existed.
      </p>
      <Link
        to="/dashboard/new-treatment"
        className="inline-flex items-center gap-2 px-4 py-2  text-white rounded-xl font-bold "
      >
        <ArrowLeft size={16} />
        Back
      </Link>
    </div>
  );
}

function ErrorCard({ requestId }: { requestId: string | null }) {
  return (
    <div className="bg-white border border-red-200 rounded-xl p-6 flex items-start gap-3">
      <AlertCircle size={20} className="text-red-700 mt-0.5" />
      <div>
        <p className="font-bold text-slate-900">
          Could not load this treatment.
        </p>
        <p className="text-sm text-slate-500 mt-1">
          Please retry. If it keeps failing, share this reference ID with the
          team: <code className="text-slate-700">{requestId ?? "unknown"}</code>
        </p>
      </div>
    </div>
  );
}

function Section({
  title,
  icon,
  children,
}: {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="bg-white border border-slate-200 rounded-xl overflow-hidden">
      <header className="px-6 py-4 border-b border-slate-200 flex items-center gap-2">
        <span className="text-slate-500">{icon}</span>
        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500">
          {title}
        </h3>
      </header>
      <div className="p-6">{children}</div>
    </section>
  );
}

function Field({
  label,
  value,
  valueClassName = "",
}: {
  label: string;
  value: string;
  valueClassName?: string;
}) {
  return (
    <div>
      <div className="text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-1">
        {label}
      </div>
      <div className={`text-sm text-slate-900 tabular-nums ${valueClassName}`}>{value}</div>
    </div>
  );
}

function PatientCard({
  data,
  isPrivacyMode,
}: {
  data: TreatmentDetail;
  isPrivacyMode: boolean;
}) {
  const p = data.patient;
  const phi = isPrivacyMode ? "blur-sm select-none" : "";
  return (
    <Section title="Patient" icon={<User size={16} />}>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
        <Field label="Name" value={p.name} valueClassName={phi} />
        <Field label="MRN" value={p.mrn} valueClassName={phi} />
        <Field label="Date of Birth" value={p.dob} valueClassName={phi} />
        <Field label="Phone" value={p.phone} valueClassName={phi} />
      </div>
    </Section>
  );
}

function TreatmentCard({ data }: { data: TreatmentDetail }) {
  const t = data.treatment;
  return (
    <Section title="Treatment" icon={<ClipboardList size={16} />}>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-6">
        <Field label="Status" value={t.status} />
        <Field label="Created" value={formatCreatedAt(t.created_at)} />
        <Field label="Treatment ID" value={t.id} />
      </div>
      {t.clinical_objective && (
        <div className="mt-6">
          <div className="text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-1">
            Clinical Objective
          </div>
          <div className="text-sm text-slate-900">{t.clinical_objective}</div>
        </div>
      )}
    </Section>
  );
}

function MedicationsCard({ data }: { data: TreatmentDetail }) {
  return (
    <Section title="Medications" icon={<Pill size={16} />}>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-[11px] font-bold uppercase tracking-wider text-slate-500 border-b border-slate-200">
              <th className="text-left py-2 pr-4 w-12">#</th>
              <th className="text-left py-2 pr-4">Name</th>
              <th className="text-left py-2 pr-4">Dosage</th>
              <th className="text-left py-2 pr-4">Frequency</th>
              <th className="text-left py-2 pr-4">Duration</th>
              <th className="text-left py-2 pr-4">Objective</th>
            </tr>
          </thead>
          <tbody>
            {data.medications.map((m, i) => (
              <tr key={m.id} className={i % 2 === 1 ? "bg-slate-50" : ""}>
                <td className="py-2 pr-4 text-slate-500 tabular-nums">
                  {m.ordinal + 1}
                </td>
                <td className="py-2 pr-4 text-slate-900 font-medium">
                  {m.name}
                </td>
                <td className="py-2 pr-4 text-slate-700 tabular-nums">
                  {m.dosage}
                </td>
                <td className="py-2 pr-4 text-slate-700">{m.frequency}</td>
                <td className="py-2 pr-4 text-slate-700 tabular-nums">
                  {m.duration}
                </td>
                <td className="py-2 pr-4 text-slate-500">
                  {m.objective ?? "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Section>
  );
}
