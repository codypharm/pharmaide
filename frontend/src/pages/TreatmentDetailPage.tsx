import { useEffect, useState } from "react";
import { Link, useOutletContext, useParams } from "react-router-dom";
import {
  ArrowLeft,
  ClipboardList,
  Pill,
  User,
  Loader2,
  AlertCircle,
  Brain,
  Play,
} from "lucide-react";

import { ApiError, NotFoundError } from "../api/client";
import {
  getTreatment,
  triggerAnalysis,
  type AnalysisResult,
  type DDIWarning,
  type KBCitation,
  type MedicationGrounding,
  type ReminderSlot,
  type TreatmentDetail,
} from "../api/treatments";
import { useAnalysisStatus } from "../hooks/useAnalysisStatus";

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
  const [activeTab, setActiveTab] = useState<"overview" | "reasoning">("overview");

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
            <TreatmentTabs activeTab={activeTab} onChange={setActiveTab} />
            {activeTab === "overview" ? (
              <>
                <PatientCard data={state.data} isPrivacyMode={isPrivacyMode} />
                <TreatmentCard data={state.data} />
                <MedicationsCard data={state.data} />
              </>
            ) : (
              <ReasoningTab treatmentId={state.data.treatment.id} />
            )}
          </>
        )}
      </div>
    </div>
  );
}

function TreatmentTabs({
  activeTab,
  onChange,
}: {
  activeTab: "overview" | "reasoning";
  onChange: (tab: "overview" | "reasoning") => void;
}) {
  return (
    <div
      role="tablist"
      aria-label="Treatment detail sections"
      className="inline-flex w-fit gap-1 rounded-lg border border-slate-200 bg-slate-100 p-1"
    >
      <button
        role="tab"
        aria-selected={activeTab === "overview"}
        type="button"
        onClick={() => onChange("overview")}
        className={`inline-flex cursor-pointer items-center gap-2 rounded-md border px-3 py-2 text-sm font-bold transition-colors ${
          activeTab === "overview"
            ? "border-slate-300 bg-white text-slate-950"
            : "border-transparent text-slate-500 hover:bg-white hover:text-slate-800"
        }`}
      >
        <ClipboardList size={15} />
        Overview
      </button>
      <button
        role="tab"
        aria-selected={activeTab === "reasoning"}
        type="button"
        onClick={() => onChange("reasoning")}
        className={`inline-flex cursor-pointer items-center gap-2 rounded-md border px-3 py-2 text-sm font-bold transition-colors ${
          activeTab === "reasoning"
            ? "border-slate-300 bg-white text-slate-950"
            : "border-transparent text-slate-500 hover:bg-white hover:text-slate-800"
        }`}
      >
        <Brain size={15} />
        Reasoning
      </button>
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
        to="/dashboard/ingestions"
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

function ReasoningTab({ treatmentId }: { treatmentId: string }) {
  const analysis = useAnalysisStatus(treatmentId);
  const [isStarting, setIsStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const [isConfirmingRerun, setIsConfirmingRerun] = useState(false);

  async function handleStartAnalysis(force = false): Promise<void> {
    setIsStarting(true);
    setStartError(null);
    try {
      if (force) {
        await triggerAnalysis(treatmentId, { force: true });
      } else {
        await triggerAnalysis(treatmentId);
      }
      setIsConfirmingRerun(false);
      await analysis.refresh();
    } catch {
      setStartError("Could not start analysis.");
    } finally {
      setIsStarting(false);
    }
  }

  if (analysis.status === "loading") {
    return <LoadingCard />;
  }

  if (analysis.error) {
    return (
      <Section title="Reasoning" icon={<Brain size={16} />}>
        <div className="flex items-start gap-3 text-sm text-red-700">
          <AlertCircle size={18} className="mt-0.5" />
          <span>Could not load analysis status.</span>
        </div>
      </Section>
    );
  }

  if (analysis.data === null) {
    return (
      <Section title="Reasoning" icon={<Brain size={16} />}>
        <div className="flex items-center justify-between gap-6">
          <div>
            <p className="text-sm font-bold text-slate-900">
              No analysis has been run for this treatment.
            </p>
            {startError && <p className="mt-2 text-sm text-red-700">{startError}</p>}
          </div>
          <button
            type="button"
            onClick={() => void handleStartAnalysis()}
            disabled={isStarting}
            className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-4 py-2 text-sm font-bold text-white disabled:cursor-not-allowed disabled:bg-slate-400"
          >
            {isStarting ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
            Run Analysis
          </button>
        </div>
      </Section>
    );
  }

  const isActiveAnalysis =
    analysis.data.status === "pending" || analysis.data.status === "running";

  return (
    <Section title="Reasoning" icon={<Brain size={16} />}>
      <AnalysisStatusHeader
        status={analysis.data.status}
        result={analysis.data.result}
        isStarting={isStarting}
        isConfirmingRerun={isConfirmingRerun}
        onStartRerun={() => setIsConfirmingRerun(true)}
        onCancelRerun={() => setIsConfirmingRerun(false)}
        onConfirmRerun={() => void handleStartAnalysis(true)}
      />
      {startError && <p className="mt-3 text-sm text-red-700">{startError}</p>}
      {analysis.data.result ? (
        <AnalysisResultView result={analysis.data.result} />
      ) : isActiveAnalysis ? (
        <ActiveAnalysisNotice status={analysis.data.status} />
      ) : (
        <p className="mt-6 text-sm text-slate-500">
          Analysis result is not available yet.
        </p>
      )}
    </Section>
  );
}

function ActiveAnalysisNotice({ status }: { status: string }) {
  return (
    <div className="mt-6 flex items-start gap-3 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
      <Loader2 size={18} className="mt-0.5 animate-spin text-slate-600" />
      <div>
        <p className="text-sm font-bold text-slate-900">Analysis in progress</p>
        <p className="mt-1 text-sm text-slate-500">
          Current status is {status}. This page is polling for the completed reasoning result.
        </p>
      </div>
    </div>
  );
}

function AnalysisStatusHeader({
  status,
  result,
  isStarting,
  isConfirmingRerun,
  onStartRerun,
  onCancelRerun,
  onConfirmRerun,
}: {
  status: string;
  result: AnalysisResult | null;
  isStarting: boolean;
  isConfirmingRerun: boolean;
  onStartRerun: () => void;
  onCancelRerun: () => void;
  onConfirmRerun: () => void;
}) {
  const canRerun = status !== "pending" && status !== "running";

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Field label="Analysis Status" value={status} />
        <div className="flex flex-wrap items-center gap-2">
          {result?.partial_results && <StatusChip label="Partial Analysis" />}
          {result?.degraded && <StatusChip label="Degraded" />}
          {canRerun && (
            <button
              type="button"
              onClick={onStartRerun}
              disabled={isStarting}
              className="inline-flex cursor-pointer items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-bold text-slate-800 hover:bg-slate-50 disabled:cursor-not-allowed disabled:text-slate-400"
            >
              Re-run
            </button>
          )}
        </div>
      </div>
      {canRerun && isConfirmingRerun && (
        <div className="flex flex-wrap items-center justify-between gap-3 border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-950">
          <span>Replace the current analysis with a fresh run?</span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onCancelRerun}
              className="cursor-pointer rounded-md border border-amber-300 bg-white px-3 py-1.5 font-bold text-amber-950"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={onConfirmRerun}
              disabled={isStarting}
              className="cursor-pointer rounded-md bg-slate-900 px-3 py-1.5 font-bold text-white disabled:cursor-not-allowed disabled:bg-slate-400"
            >
              Confirm Re-run
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function AnalysisResultView({ result }: { result: AnalysisResult }) {
  return (
    <div className="mt-6 space-y-6">
      <ClinicalSummary result={result} />
      <SourcesList citations={result.kb_citations ?? []} />
      <GroundingsList groundings={result.groundings} />
      <InteractionsList warnings={result.ddi_warnings} />
      <SchedulePreview
        groundings={result.groundings}
        reminders={result.schedule?.reminders ?? []}
      />
    </div>
  );
}

function ClinicalSummary({ result }: { result: AnalysisResult }) {
  return (
    <div className="border-t border-slate-200 pt-5">
      <SubsectionTitle>Clinical Summary</SubsectionTitle>
      {result.reasoning ? (
        <div className="mt-3 space-y-3">
          <p className="text-sm leading-6 text-slate-900">{result.reasoning.summary}</p>
          {result.reasoning.red_flags.length > 0 && (
            <div className="space-y-2">
              <div className="text-[11px] font-bold uppercase tracking-wider text-red-700">
                Red Flags
              </div>
              <ul className="space-y-1">
                {result.reasoning.red_flags.map((flag) => (
                  <li key={flag} className="text-sm text-red-800">
                    {flag}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      ) : (
        <EmptyAnalysisText>No clinical summary was produced.</EmptyAnalysisText>
      )}
    </div>
  );
}

function SourcesList({ citations }: { citations: KBCitation[] }) {
  return (
    <div className="border-t border-slate-200 pt-5">
      <SubsectionTitle>Sources</SubsectionTitle>
      {citations.length > 0 ? (
        <div className="mt-3 grid gap-3 lg:grid-cols-2">
          {citations.map((citation) => (
            <div
              key={citation.chunk_id}
              className="border border-slate-200 bg-slate-50 px-4 py-3"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <Link
                    to={`/dashboard/knowledge/${citation.document_id}`}
                    className="text-sm font-bold text-slate-900 hover:text-blue-700"
                  >
                    {citation.document_title}
                  </Link>
                  <p className="mt-1 text-xs font-bold uppercase tracking-wider text-slate-500">
                    Relevance {formatRelevance(citation.score)}
                  </p>
                </div>
              </div>
              <p className="mt-3 text-sm leading-6 text-slate-700">{citation.text}</p>
            </div>
          ))}
        </div>
      ) : (
        <EmptyAnalysisText>No uploaded clinical assets were cited.</EmptyAnalysisText>
      )}
    </div>
  );
}

function GroundingsList({ groundings }: { groundings: MedicationGrounding[] }) {
  return (
    <div className="border-t border-slate-200 pt-5">
      <SubsectionTitle>Groundings</SubsectionTitle>
      {groundings.length > 0 ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {groundings.map((grounding) => (
            <span
              key={grounding.medication_id}
              className={`rounded-full border px-3 py-1 text-sm font-bold ${
                grounding.rxcui
                  ? "border-slate-200 bg-slate-50 text-slate-800"
                  : "border-red-200 bg-red-50 text-red-800"
              }`}
            >
              {grounding.medication_name} /{" "}
              {grounding.rxcui ? `RxCUI ${grounding.rxcui}` : "Unmatched"}
            </span>
          ))}
        </div>
      ) : (
        <EmptyAnalysisText>No medication groundings were produced.</EmptyAnalysisText>
      )}
    </div>
  );
}

function InteractionsList({ warnings }: { warnings: DDIWarning[] }) {
  return (
    <div className="border-t border-slate-200 pt-5">
      <SubsectionTitle>Interactions</SubsectionTitle>
      {warnings.length > 0 ? (
        <div className="mt-3 space-y-2">
          {warnings.map((warning) => (
            <div
              key={`${warning.source}-${warning.description}`}
              className={`border px-3 py-2 text-sm ${
                warning.severity === "major"
                  ? "border-red-200 bg-red-50 text-red-900"
                  : "border-amber-200 bg-amber-50 text-amber-900"
              }`}
            >
              <div className="font-bold uppercase tracking-wider">
                {warning.severity}
              </div>
              <div className="mt-1">{warning.description}</div>
            </div>
          ))}
        </div>
      ) : (
        <EmptyAnalysisText>No interaction warnings were returned.</EmptyAnalysisText>
      )}
    </div>
  );
}

function SchedulePreview({
  groundings,
  reminders,
}: {
  groundings: MedicationGrounding[];
  reminders: ReminderSlot[];
}) {
  const medicationNames = new Map(
    groundings.map((grounding) => [grounding.medication_id, grounding.medication_name]),
  );
  return (
    <div className="border-t border-slate-200 pt-5">
      <SubsectionTitle>Schedule Preview</SubsectionTitle>
      {reminders.length > 0 && (
        <p className="mt-2 text-xs font-semibold text-slate-500">
          Planned relative schedule. Adherence state is not tracked here.
        </p>
      )}
      {reminders.length > 0 ? (
        <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          {reminders.map((reminder, index) => (
            <div
              key={`${reminder.medication_id}-${reminder.offset_from_start}`}
              className="border border-slate-200 bg-slate-50 px-3 py-2 tabular-nums"
            >
              <div className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
                Reminder {index + 1}
              </div>
              <div className="mt-1 text-sm font-bold text-slate-900">
                {medicationNames.get(reminder.medication_id) ?? "Medication"}
              </div>
              <div className="mt-1 text-sm font-bold text-slate-900">
                {reminder.human_label}
              </div>
              <div className="mt-1 flex items-center gap-1 text-xs text-slate-500">
                <span>{formatReminderTiming(reminder.offset_from_start)}</span>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <EmptyAnalysisText>No schedule reminders were generated.</EmptyAnalysisText>
      )}
    </div>
  );
}

function formatRelevance(score: number): string {
  const boundedScore = Math.max(0, Math.min(1, score));
  return `${Math.round(boundedScore * 100)}%`;
}

function formatReminderTiming(offset: string): string {
  const match = offset.match(
    /^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?)?$/,
  );
  if (!match) return offset;

  const [, days, hours, minutes, seconds] = match;
  const totalSeconds =
    Number(days ?? 0) * 86_400 +
    Number(hours ?? 0) * 3_600 +
    Number(minutes ?? 0) * 60 +
    Number(seconds ?? 0);
  const plannedDay = Math.floor(totalSeconds / 86_400) + 1;
  const secondsWithinDay = totalSeconds % 86_400;
  const timeParts = [
    Math.floor(secondsWithinDay / 3_600)
      ? `${Math.floor(secondsWithinDay / 3_600)}h`
      : null,
    Math.floor((secondsWithinDay % 3_600) / 60)
      ? `${Math.floor((secondsWithinDay % 3_600) / 60)}m`
      : null,
    secondsWithinDay % 60 ? `${secondsWithinDay % 60}s` : null,
  ].filter(Boolean);
  const relativeTime = timeParts.length > 0 ? `+${timeParts.join(" ")}` : "at start";

  return `Planned Day ${plannedDay} · ${relativeTime}`;
}

function StatusChip({ label }: { label: string }) {
  return (
    <span className="rounded-full bg-amber-100 px-3 py-1 text-xs font-bold uppercase tracking-wider text-amber-800">
      {label}
    </span>
  );
}

function SubsectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h4 className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
      {children}
    </h4>
  );
}

function EmptyAnalysisText({ children }: { children: React.ReactNode }) {
  return <p className="mt-3 text-sm text-slate-500">{children}</p>;
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
