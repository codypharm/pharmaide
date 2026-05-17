import { type FormEvent, useEffect, useState } from "react";
import { Link, useOutletContext, useParams } from "react-router-dom";
import {
  Archive,
  ArrowLeft,
  CheckCircle2,
  ClipboardList,
  Pill,
  User,
  Loader2,
  AlertCircle,
  Brain,
  MessageSquare,
  Play,
  Plus,
  Send,
  ShieldCheck,
} from "lucide-react";

import { ApiError, ConflictError, NotFoundError } from "../api/client";
import {
  addMedicationToTreatment,
  archiveTreatment,
  createPatientCheckIn,
  discontinueMedication,
  getCompletionReport,
  getAnalysis,
  getTreatment,
  listAdherenceEvents,
  listPatientCheckIns,
  startTreatmentCycle,
  terminateTreatment,
  triggerAnalysis,
  updateTreatmentClinicalObjective,
  type AdherenceEventStatus,
  type AdherenceEventView,
  type AnalysisResult,
  type ClinicalSafetyReview,
  type CourseCompletionReport,
  type DDIWarning,
  type KBCitation,
  type MedicationGrounding,
  type PatientCheckInReportType,
  type PatientCheckInView,
  type ReminderSlot,
  type TreatmentAnalysisRow,
  type TreatmentAnalysisSnapshot,
  type TreatmentDetail,
  type TreatmentView,
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

type ActivationAnalysisState =
  | { kind: "loading" }
  | { kind: "ok"; ready: boolean; completedAt: string | null }
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
  const [activeTab, setActiveTab] = useState<"overview" | "reasoning">(
    "overview",
  );
  const [startCycleState, setStartCycleState] = useState<
    { kind: "idle" | "starting" } | { kind: "error"; requestId: string | null }
  >({ kind: "idle" });
  const [activationAnalysis, setActivationAnalysis] =
    useState<ActivationAnalysisState>({
      kind: "loading",
    });

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

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    setActivationAnalysis({ kind: "loading" });
    getAnalysis(id)
      .then((analysis) => {
        if (cancelled) return;
        const completedAnalysis = completedAnalysisForCycle(analysis);
        setActivationAnalysis({
          kind: "ok",
          ready: Boolean(completedAnalysis),
          completedAt: completedAnalysis?.completed_at ?? null,
        });
      })
      .catch((err) => {
        if (cancelled) return;
        setActivationAnalysis({
          kind: "error",
          requestId: err instanceof ApiError ? err.requestId : null,
        });
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  const handleStartCycle = async () => {
    if (state.kind !== "ok") return;
    setStartCycleState({ kind: "starting" });
    try {
      const treatment = await startTreatmentCycle(state.data.treatment.id);
      setState({
        kind: "ok",
        data: { ...state.data, treatment },
      });
      setStartCycleState({ kind: "idle" });
    } catch (err) {
      if (
        err instanceof ConflictError &&
        err.errorCode === "analysis_not_completed"
      ) {
        setActivationAnalysis({ kind: "ok", ready: false, completedAt: null });
        setStartCycleState({ kind: "idle" });
        return;
      }
      setStartCycleState({
        kind: "error",
        requestId: err instanceof ApiError ? err.requestId : null,
      });
    }
  };

  const handleTreatmentArchived = (treatment: TreatmentView) => {
    if (state.kind !== "ok") return;
    setState({
      kind: "ok",
      data: { ...state.data, treatment },
    });
  };

  const handleTreatmentTerminated = (treatment: TreatmentView) => {
    if (state.kind !== "ok") return;
    setState({
      kind: "ok",
      data: { ...state.data, treatment },
    });
  };

  const handleTreatmentUpdated = (treatment: TreatmentView) => {
    if (state.kind !== "ok") return;
    setState({
      kind: "ok",
      data: { ...state.data, treatment },
    });
  };

  const handleTreatmentDetailReloaded = (detail: TreatmentDetail) => {
    setState({ kind: "ok", data: detail });
    if (
      detail.treatment.status === "pending" &&
      detail.treatment.automation_mode === "paused"
    ) {
      setActivationAnalysis({ kind: "ok", ready: false, completedAt: null });
    }
  };

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
                <TreatmentCard
                  data={state.data}
                  startCycleState={startCycleState}
                  activationAnalysis={activationAnalysis}
                  onStartCycle={handleStartCycle}
                  onTerminated={handleTreatmentTerminated}
                  onUpdated={handleTreatmentUpdated}
                />
                <CompletionReportCard
                  treatment={state.data.treatment}
                  onArchived={handleTreatmentArchived}
                />
                <MedicationsCard
                  data={state.data}
                  onTreatmentDetailReloaded={handleTreatmentDetailReloaded}
                />
                <PatientUpdatesCard
                  treatmentId={state.data.treatment.id}
                  isPrivacyMode={isPrivacyMode}
                />
              </>
            ) : (
              <ReasoningTab treatment={state.data.treatment} />
            )}
          </>
        )}
      </div>
    </div>
  );
}

type CheckInState =
  | { kind: "loading" }
  | { kind: "ok"; items: PatientCheckInView[] }
  | { kind: "error"; requestId: string | null };

const REPORT_TYPE_OPTIONS: {
  value: PatientCheckInReportType;
  label: string;
}[] = [
  { value: "not_improving", label: "Not improving" },
  { value: "side_effect", label: "Side effect" },
  { value: "feeling_better", label: "Feeling better" },
  { value: "general_update", label: "General update" },
  { value: "missed_dose", label: "Missed dose" },
];

function PatientUpdatesCard({
  treatmentId,
  isPrivacyMode,
}: {
  treatmentId: string;
  isPrivacyMode: boolean;
}) {
  const [state, setState] = useState<CheckInState>({ kind: "loading" });
  const [reportType, setReportType] =
    useState<PatientCheckInReportType>("general_update");
  const [message, setMessage] = useState("");
  const [observedAt, setObservedAt] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setState({ kind: "loading" });
    listPatientCheckIns(treatmentId)
      .then((result) => {
        if (!cancelled) setState({ kind: "ok", items: result.items });
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
  }, [treatmentId]);

  async function handleSubmit(): Promise<void> {
    if (!message.trim()) {
      setSaveError("Enter the patient-reported clinical update before saving.");
      return;
    }

    setIsSaving(true);
    setSaveError(null);
    try {
      const created = await createPatientCheckIn(treatmentId, {
        report_type: reportType,
        source: "pharmacist",
        message: message.trim(),
        observed_at: toOptionalIso(observedAt),
      });
      setState((current) =>
        current.kind === "ok"
          ? { kind: "ok", items: [created, ...current.items] }
          : current,
      );
      setMessage("");
      setObservedAt("");
      setReportType("general_update");
    } catch (err) {
      const requestId = err instanceof ApiError ? err.requestId : null;
      setSaveError(
        `Could not save patient-reported clinical update. Reference ID: ${
          requestId ?? "unknown"
        }`,
      );
    } finally {
      setIsSaving(false);
    }
  }

  const phi = isPrivacyMode ? "blur-sm select-none" : "";

  return (
    <Section
      title="Patient-Reported Updates"
      icon={<MessageSquare size={16} />}
    >
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
        <div>
          {state.kind === "loading" && (
            <div className="flex items-center gap-2 text-sm text-slate-500">
              <Loader2 size={16} className="animate-spin" />
              Loading patient-reported updates…
            </div>
          )}
          {state.kind === "error" && (
            <div className="flex items-start gap-2 text-sm text-red-700">
              <AlertCircle size={16} className="mt-0.5" />
              <span>
                Could not load patient-reported updates. Reference ID:{" "}
                {state.requestId ?? "unknown"}
              </span>
            </div>
          )}
          {state.kind === "ok" && (
            <>
              {state.items.length === 0 ? (
                <div className="border border-slate-200 bg-slate-50 px-4 py-5">
                  <p className="text-sm font-bold text-slate-900">
                    No patient-reported updates recorded
                  </p>
                  <p className="mt-1 text-sm text-slate-500">
                    Use this section when a patient reports symptoms, progress,
                    concerns, or a missed dose.
                  </p>
                </div>
              ) : (
                <div className="space-y-3">
                  {state.items.map((item) => (
                    <div
                      key={item.id}
                      className="border border-slate-200 bg-slate-50 px-4 py-3"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
                          {reportTypeLabel(item.report_type)}
                        </span>
                        <span className="text-xs font-semibold text-slate-500 tabular-nums">
                          {formatCreatedAt(item.observed_at ?? item.created_at)}
                        </span>
                      </div>
                      <p
                        className={`mt-2 text-sm leading-6 text-slate-900 ${phi}`}
                      >
                        {item.message}
                      </p>
                      <p className="mt-2 text-xs font-semibold uppercase tracking-wider text-slate-500">
                        Source: {sourceLabel(item.source)}
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>

        <form
          className="border border-slate-200 bg-white p-4"
          onSubmit={(event) => {
            event.preventDefault();
            void handleSubmit();
          }}
        >
          <div className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
            Record Clinical Update
          </div>
          <div className="mt-4 space-y-4">
            <div>
              <label
                htmlFor="patient-update-type"
                className="text-[11px] font-bold uppercase tracking-wider text-slate-500"
              >
                Update Type
              </label>
              <select
                id="patient-update-type"
                value={reportType}
                onChange={(event) =>
                  setReportType(event.target.value as PatientCheckInReportType)
                }
                className="mt-1 w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-900 focus:border-[#5548E8] focus:outline-none focus:ring-2 focus:ring-[#D9D5FB]"
              >
                {REPORT_TYPE_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label
                htmlFor="patient-update-message"
                className="text-[11px] font-bold uppercase tracking-wider text-slate-500"
              >
                Patient-Reported Update
              </label>
              <textarea
                id="patient-update-message"
                value={message}
                onChange={(event) => setMessage(event.target.value)}
                placeholder="e.g. Patient reports dizziness after the morning dose."
                className="mt-1 min-h-28 w-full resize-none rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-900 focus:border-[#5548E8] focus:outline-none focus:ring-2 focus:ring-[#D9D5FB]"
              />
            </div>
            <div>
              <label
                htmlFor="patient-update-observed-at"
                className="text-[11px] font-bold uppercase tracking-wider text-slate-500"
              >
                Observed At
              </label>
              <input
                id="patient-update-observed-at"
                type="datetime-local"
                value={observedAt}
                onChange={(event) => setObservedAt(event.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-900 focus:border-[#5548E8] focus:outline-none focus:ring-2 focus:ring-[#D9D5FB]"
              />
            </div>
            {saveError && <p className="text-sm text-red-700">{saveError}</p>}
            <button
              type="submit"
              disabled={isSaving}
              className="inline-flex w-full cursor-pointer items-center justify-center gap-2 rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-bold text-white hover:bg-slate-800 disabled:cursor-wait disabled:bg-slate-400"
            >
              {isSaving ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <Send size={16} />
              )}
              Save Clinical Update
            </button>
          </div>
        </form>
      </div>
    </Section>
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
        <div className="w-10 h-10 bg-[#F0EFFF] text-[#5548E8] rounded-xl flex items-center justify-center shadow-sm">
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

type AdherenceState =
  | { kind: "loading"; items: AdherenceEventView[] }
  | { kind: "ok"; items: AdherenceEventView[] }
  | { kind: "error"; items: AdherenceEventView[] };

function ReasoningTab({
  treatment,
}: {
  treatment: TreatmentDetail["treatment"];
}) {
  const treatmentId = treatment.id;
  const analysis = useAnalysisStatus(treatmentId);
  const [adherenceState, setAdherenceState] = useState<AdherenceState>({
    kind: "loading",
    items: [],
  });
  const [isStarting, setIsStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const [isConfirmingRerun, setIsConfirmingRerun] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setAdherenceState({ kind: "loading", items: [] });
    listAdherenceEvents(treatmentId)
      .then((result) => {
        if (!cancelled) setAdherenceState({ kind: "ok", items: result.items });
      })
      .catch(() => {
        if (!cancelled) setAdherenceState({ kind: "ok", items: [] });
      });
    return () => {
      cancelled = true;
    };
  }, [treatmentId]);

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
            {startError && (
              <p className="mt-2 text-sm text-red-700">{startError}</p>
            )}
          </div>
          <button
            type="button"
            onClick={() => void handleStartAnalysis()}
            disabled={isStarting}
            className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-4 py-2 text-sm font-bold text-white disabled:cursor-not-allowed disabled:bg-slate-400"
          >
            {isStarting ? (
              <Loader2 size={16} className="animate-spin" />
            ) : (
              <Play size={16} />
            )}
            Run Analysis
          </button>
        </div>
      </Section>
    );
  }

  const isActiveAnalysis =
    analysis.data.status === "pending" || analysis.data.status === "running";
  const displayedAnalysis = analysisToDisplay(analysis.data);
  const isShowingLastCompleted = displayedAnalysis.id !== analysis.data.id;

  return (
    <Section title="Reasoning" icon={<Brain size={16} />}>
      <AnalysisStatusHeader
        status={analysis.data.status}
        result={displayedAnalysis.result}
        isStarting={isStarting}
        isConfirmingRerun={isConfirmingRerun}
        onStartRerun={() => setIsConfirmingRerun(true)}
        onCancelRerun={() => setIsConfirmingRerun(false)}
        onConfirmRerun={() => void handleStartAnalysis(true)}
      />
      {startError && <p className="mt-3 text-sm text-red-700">{startError}</p>}
      {isActiveAnalysis && (
        <ActiveAnalysisNotice status={analysis.data.status} />
      )}
      {isShowingLastCompleted && (
        <LastCompletedAnalysisNotice
          latestStatus={analysis.data.status}
          errorText={analysis.data.error_text}
        />
      )}
      {displayedAnalysis.result ? (
        <AnalysisResultView
          result={displayedAnalysis.result}
          adherenceState={adherenceState}
          treatmentStartAt={treatment.treatment_start_at}
        />
      ) : (
        <p className="mt-6 text-sm text-slate-500">
          Analysis result is not available yet.
        </p>
      )}
    </Section>
  );
}

function analysisToDisplay(
  analysis: TreatmentAnalysisSnapshot & {
    last_completed?: TreatmentAnalysisSnapshot | null;
  },
): TreatmentAnalysisSnapshot {
  if (analysis.result) return analysis;
  if (analysis.last_completed?.result) return analysis.last_completed;
  return analysis;
}

function ActiveAnalysisNotice({ status }: { status: string }) {
  return (
    <div className="mt-6 flex items-start gap-3 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
      <Loader2 size={18} className="mt-0.5 animate-spin text-slate-600" />
      <div>
        <p className="text-sm font-bold text-slate-900">Analysis in progress</p>
        <p className="mt-1 text-sm text-slate-500">
          Current status is {status}. This page is polling for the completed
          reasoning result.
        </p>
      </div>
    </div>
  );
}

function LastCompletedAnalysisNotice({
  latestStatus,
  errorText,
}: {
  latestStatus: string;
  errorText: string | null;
}) {
  return (
    <div className="mt-6 flex items-start gap-3 border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950">
      <AlertCircle size={18} className="mt-0.5 shrink-0" />
      <div>
        <p className="font-bold">Latest analysis attempt could not complete</p>
        <p className="mt-1">
          {analysisFailureLabel(errorText)}. Showing the most recent completed
          analysis below.
        </p>
        <p className="mt-1 text-xs font-semibold uppercase tracking-wider text-amber-800">
          Latest attempt status: {latestStatus}
        </p>
      </div>
    </div>
  );
}

function analysisFailureLabel(errorText: string | null): string {
  switch (errorText) {
    case "analysis_timeout":
      return "Analysis took too long";
    case "analysis_rate_limited":
      return "Analysis service is busy";
    case "analysis_failed":
      return "Analysis attempt failed";
    default:
      return "Analysis attempt could not complete";
  }
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
              Run again
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
              Confirm Run Again
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function AnalysisResultView({
  result,
  adherenceState,
  treatmentStartAt,
}: {
  result: AnalysisResult;
  adherenceState: AdherenceState;
  treatmentStartAt: string | null;
}) {
  return (
    <div className="mt-6 space-y-6">
      <ClinicalSummary result={result} />
      <SourcesList citations={result.kb_citations ?? []} />
      <ClinicalSafetyReviewPanel review={result.clinical_safety_review} />
      <GroundingsList groundings={result.groundings} />
      <InteractionsList warnings={result.ddi_warnings} />
      <SchedulePreview
        groundings={result.groundings}
        reminders={result.schedule?.reminders ?? []}
        adherenceState={adherenceState}
        treatmentStartAt={treatmentStartAt}
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
          <p className="text-sm leading-6 text-slate-900">
            {result.reasoning.summary}
          </p>
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
                    className="text-sm font-bold text-slate-900 hover:text-[#5548E8]"
                  >
                    {citation.document_title}
                  </Link>
                  <p className="mt-1 text-xs font-bold uppercase tracking-wider text-slate-500">
                    {sourceTypeLabel(citation.source_type)} · Relevance{" "}
                    {formatRelevance(citation.score)}
                  </p>
                </div>
              </div>
              <p className="mt-3 text-sm leading-6 text-slate-700">
                {citation.text}
              </p>
            </div>
          ))}
        </div>
      ) : (
        <EmptyAnalysisText>
          No uploaded clinical assets were cited.
        </EmptyAnalysisText>
      )}
    </div>
  );
}

function ClinicalSafetyReviewPanel({
  review,
}: {
  review: ClinicalSafetyReview | null | undefined;
}) {
  if (!review) return null;

  return (
    <div className="border-t border-slate-200 pt-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <SubsectionTitle>AI Safety Review</SubsectionTitle>
        <span className="inline-flex items-center gap-1 rounded-full border border-amber-200 bg-amber-50 px-2.5 py-1 text-[11px] font-bold uppercase tracking-wider text-amber-900">
          <ShieldCheck size={13} aria-hidden="true" />
          Requires pharmacist review
        </span>
      </div>
      <p className="mt-2 text-xs font-semibold text-slate-500">
        Interim model review, not a licensed interaction database result.
        Confidence {formatRelevance(review.confidence)}.
      </p>
      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <ReviewList
          title="Possible Interactions"
          items={review.possible_interactions}
        />
        <ReviewList
          title="Monitoring Concerns"
          items={review.monitoring_concerns}
        />
        <ReviewList
          title="Counseling Points"
          items={review.counseling_points}
        />
        <ReviewList
          title="Missing Information"
          items={review.missing_information}
        />
      </div>
    </div>
  );
}

function ReviewList({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="border border-slate-200 bg-slate-50 px-4 py-3">
      <div className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
        {title}
      </div>
      {items.length > 0 ? (
        <ul className="mt-2 space-y-1">
          {items.map((item) => (
            <li key={item} className="text-sm leading-6 text-slate-800">
              {item}
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-sm text-slate-500">None noted.</p>
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
        <EmptyAnalysisText>
          No medication groundings were produced.
        </EmptyAnalysisText>
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
        <EmptyAnalysisText>
          No interaction warnings were returned.
        </EmptyAnalysisText>
      )}
    </div>
  );
}

function SchedulePreview({
  groundings,
  reminders,
  adherenceState,
  treatmentStartAt,
}: {
  groundings: MedicationGrounding[];
  reminders: ReminderSlot[];
  adherenceState: AdherenceState;
  treatmentStartAt: string | null;
}) {
  const medicationNames = new Map(
    groundings.map((grounding) => [
      grounding.medication_id,
      grounding.medication_name,
    ]),
  );
  const adherenceByReminder = latestAdherenceByReminder(adherenceState.items);

  return (
    <div className="border-t border-slate-200 pt-5">
      <SubsectionTitle>Schedule Preview</SubsectionTitle>
      {reminders.length > 0 && (
        <div className="mt-2 space-y-1 text-xs font-semibold text-slate-500">
          <p>Planned relative schedule with recorded adherence state.</p>
          {adherenceState.kind === "loading" && <p>Loading adherence state…</p>}
          {adherenceState.kind === "error" && (
            <p className="text-amber-700">Could not load adherence state.</p>
          )}
        </div>
      )}
      {reminders.length > 0 ? (
        <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
          {reminders.map((reminder, index) => {
            const scheduledFor = scheduledForIso(
              treatmentStartAt,
              reminder.offset_from_start,
            );
            const key = adherenceKey(reminder.medication_id, scheduledFor);
            const event = adherenceByReminder.get(key);

            return (
              <div
                key={`${reminder.medication_id}-${reminder.offset_from_start}`}
                className="border border-slate-200 bg-slate-50 px-3 py-2 tabular-nums"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
                    Reminder {index + 1}
                  </div>
                  <AdherenceStatusChip event={event} />
                </div>
                <div className="mt-1 text-sm font-bold text-slate-900">
                  {medicationNames.get(reminder.medication_id) ?? "Medication"}
                </div>
                <div className="mt-1 text-sm font-bold text-slate-900">
                  {reminder.human_label}
                </div>
                <div className="mt-1 flex items-center gap-1 text-xs text-slate-500">
                  <span>
                    {formatReminderTiming(reminder.offset_from_start)}
                  </span>
                </div>
                {event && (
                  <p className="mt-2 text-xs font-semibold text-slate-500">
                    Recorded by {sourceLabel(event.source)}
                  </p>
                )}
              </div>
            );
          })}
        </div>
      ) : (
        <EmptyAnalysisText>
          No schedule reminders were generated.
        </EmptyAnalysisText>
      )}
    </div>
  );
}

function AdherenceStatusChip({
  event,
}: {
  event: AdherenceEventView | undefined;
}) {
  if (!event) {
    return (
      <span className="rounded-full border border-slate-200 bg-white px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-slate-500">
        Planned
      </span>
    );
  }

  const styles: Record<AdherenceEventStatus, string> = {
    taken: "border-emerald-200 bg-emerald-50 text-emerald-700",
    missed: "border-red-200 bg-red-50 text-red-700",
    held: "border-amber-200 bg-amber-50 text-amber-800",
    skipped: "border-slate-200 bg-white text-slate-600",
  };

  return (
    <span
      className={`rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ${styles[event.status as AdherenceEventStatus]}`}
    >
      {adherenceStatusLabel(event.status)}
    </span>
  );
}

function formatRelevance(score: number): string {
  const boundedScore = Math.max(0, Math.min(1, score));
  return `${Math.round(boundedScore * 100)}%`;
}

function sourceTypeLabel(sourceType: KBCitation["source_type"]): string {
  if (sourceType === "dailymed") return "Verified medical reference";
  return "Clinic asset";
}

function formatReminderTiming(offset: string): string {
  const totalSeconds = durationToSeconds(offset);
  if (totalSeconds === null) return offset;

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
  const relativeTime =
    timeParts.length > 0 ? `+${timeParts.join(" ")}` : "at start";

  return `Planned Day ${plannedDay} · ${relativeTime}`;
}

function durationToSeconds(offset: string): number | null {
  const match = offset.match(
    /^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?)?$/,
  );
  if (!match) return null;

  const [, days, hours, minutes, seconds] = match;
  return (
    Number(days ?? 0) * 86_400 +
    Number(hours ?? 0) * 3_600 +
    Number(minutes ?? 0) * 60 +
    Number(seconds ?? 0)
  );
}

function scheduledForIso(
  treatmentStartAt: string | null,
  offset: string,
): string | null {
  if (!treatmentStartAt) return null;
  const start = new Date(treatmentStartAt);
  const offsetSeconds = durationToSeconds(offset);
  if (Number.isNaN(start.getTime()) || offsetSeconds === null) return null;
  return new Date(start.getTime() + offsetSeconds * 1000).toISOString();
}

function latestAdherenceByReminder(
  events: AdherenceEventView[],
): Map<string, AdherenceEventView> {
  const latest = new Map<string, AdherenceEventView>();
  for (const event of events) {
    // The API returns newest first; keep the first event for each scheduled dose.
    const key = adherenceKey(
      event.medication_id,
      normaliseEventTime(event.scheduled_for),
    );
    if (!latest.has(key)) latest.set(key, event);
  }
  return latest;
}

function adherenceKey(
  medicationId: string,
  scheduledFor: string | null,
): string {
  return `${medicationId}:${normaliseEventTime(scheduledFor) ?? "unscheduled"}`;
}

function normaliseEventTime(value: string | null): string | null {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toISOString();
}

function adherenceStatusLabel(status: string): string {
  switch (status) {
    case "taken":
      return "Taken";
    case "missed":
      return "Missed";
    case "held":
      return "Held";
    case "skipped":
      return "Skipped";
    default:
      return status;
  }
}

function toOptionalIso(value: string): string | null {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
}

function reportTypeLabel(reportType: string): string {
  return (
    REPORT_TYPE_OPTIONS.find((option) => option.value === reportType)?.label ??
    reportType.replaceAll("_", " ")
  );
}

function sourceLabel(source: string): string {
  switch (source) {
    case "patient":
      return "Patient";
    case "pharmacist":
      return "Pharmacist";
    case "system":
      return "System";
    default:
      return source;
  }
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
      <div className={`text-sm text-slate-900 tabular-nums ${valueClassName}`}>
        {value}
      </div>
    </div>
  );
}

function StatusField({ status }: { status: string }) {
  return (
    <div>
      <div className="text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-1">
        Status
      </div>
      <TreatmentStatusPill status={status} />
    </div>
  );
}

function TreatmentStatusPill({ status }: { status: string }) {
  const tone =
    status === "pending"
      ? "bg-amber-50 text-amber-800 border-amber-200"
      : status === "active"
        ? "bg-[#F0EFFF] text-[#463AD4] border-[#D9D5FB]"
        : status === "completed"
          ? "bg-emerald-50 text-emerald-800 border-emerald-200"
          : "bg-slate-50 text-slate-700 border-slate-200";
  return (
    <span
      className={`inline-flex rounded-full border px-2.5 py-1 text-[11px] font-bold uppercase tracking-wider ${tone}`}
    >
      {treatmentStatusLabel(status)}
    </span>
  );
}

function treatmentStatusLabel(status: string): string {
  switch (status) {
    case "pending":
      return "Pending";
    case "active":
      return "Active";
    case "completed":
      return "Completed";
    case "terminated":
      return "Terminated";
    default:
      return status;
  }
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
      <div className="mt-6">
        <div className="text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-2">
          Known Allergies
        </div>
        {p.allergies.length > 0 ? (
          <div className={`flex flex-wrap gap-2 ${phi}`}>
            {p.allergies.map((allergy) => (
              <span
                key={allergy}
                className="rounded-full border border-red-200 bg-red-50 px-2.5 py-1 text-[11px] font-bold text-red-700"
              >
                {allergy}
              </span>
            ))}
          </div>
        ) : (
          <p className="text-sm font-semibold text-slate-500">
            No allergies recorded.
          </p>
        )}
      </div>
    </Section>
  );
}

function TreatmentCard({
  data,
  startCycleState,
  activationAnalysis,
  onStartCycle,
  onTerminated,
  onUpdated,
}: {
  data: TreatmentDetail;
  startCycleState:
    | { kind: "idle" | "starting" }
    | { kind: "error"; requestId: string | null };
  activationAnalysis: ActivationAnalysisState;
  onStartCycle: () => void;
  onTerminated: (treatment: TreatmentView) => void;
  onUpdated: (treatment: TreatmentView) => void;
}) {
  const t = data.treatment;
  const isActive = t.status === "active";
  const isCompleted = t.status === "completed";
  const isPending = t.status === "pending";
  const isTerminated = t.status === "terminated";
  const isStarting = startCycleState.kind === "starting";
  const analysisReady =
    activationAnalysis.kind === "ok" && activationAnalysis.ready;
  const planChangeNeedsAnalysis =
    isPending && treatmentPlanChangedAfterAnalysis(data, activationAnalysis);
  const canStart =
    isPending && !isStarting && analysisReady && !planChangeNeedsAnalysis;
  const [terminateState, setTerminateState] = useState<
    | { kind: "idle" }
    | { kind: "confirming" }
    | { kind: "saving" }
    | { kind: "error"; requestId: string | null }
  >({ kind: "idle" });
  const canTerminate = isActive && terminateState.kind !== "saving";
  const [objectiveState, setObjectiveState] = useState<
    { kind: "idle" | "saving" } | { kind: "error"; requestId: string | null }
  >({ kind: "idle" });

  async function handleTerminate(): Promise<void> {
    if (!canTerminate) return;
    setTerminateState({ kind: "saving" });
    try {
      const treatment = await terminateTreatment(t.id);
      onTerminated(treatment);
      setTerminateState({ kind: "idle" });
    } catch (err) {
      setTerminateState({
        kind: "error",
        requestId: err instanceof ApiError ? err.requestId : null,
      });
    }
  }

  async function handleObjectiveSave(value: string): Promise<void> {
    setObjectiveState({ kind: "saving" });
    try {
      const treatment = await updateTreatmentClinicalObjective(t.id, {
        clinical_objective: value.trim() || null,
      });
      onUpdated(treatment);
      setObjectiveState({ kind: "idle" });
    } catch (err) {
      setObjectiveState({
        kind: "error",
        requestId: err instanceof ApiError ? err.requestId : null,
      });
    }
  }

  return (
    <Section title="Treatment" icon={<ClipboardList size={16} />}>
      {planChangeNeedsAnalysis && <TreatmentPlanChangedNotice />}
      <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
        <div className="grid flex-1 grid-cols-2 gap-6 md:grid-cols-3">
          <StatusField status={t.status} />
          <Field
            label="Treatment Starts"
            value={
              t.treatment_start_at
                ? formatCreatedAt(t.treatment_start_at)
                : "Not set"
            }
          />
          <Field label="Created" value={formatCreatedAt(t.created_at)} />
          <Field label="Treatment ID" value={t.id} />
        </div>
        {isPending && (
          <div className="flex min-w-48 flex-col items-start gap-2 lg:items-end">
            <button
              type="button"
              onClick={onStartCycle}
              disabled={!canStart}
              className="inline-flex cursor-pointer items-center justify-center gap-2 rounded-lg bg-[#5548E8] px-4 py-2 text-sm font-bold text-white transition-colors hover:bg-[#463AD4] disabled:cursor-wait disabled:bg-slate-400"
            >
              {isStarting ? (
                <>
                  <Loader2 size={15} className="animate-spin" />
                  Starting
                </>
              ) : (
                <>
                  <Play size={15} />
                  Start Cycle
                </>
              )}
            </button>
            {activationAnalysis.kind === "loading" && (
              <p className="max-w-64 text-xs font-semibold text-slate-500">
                Checking analysis status before cycle start.
              </p>
            )}
            {activationAnalysis.kind === "ok" && !activationAnalysis.ready && (
              <p className="max-w-64 text-xs font-semibold text-amber-700">
                Complete analysis before starting cycle.
              </p>
            )}
            {activationAnalysis.kind === "ok" &&
              activationAnalysis.ready &&
              planChangeNeedsAnalysis && (
                <p className="max-w-64 text-xs font-semibold text-amber-700">
                  Rerun analysis before starting cycle.
                </p>
              )}
            {activationAnalysis.kind === "error" && (
              <p className="max-w-64 text-xs font-semibold text-red-700">
                Could not verify analysis status. Reference ID:{" "}
                {activationAnalysis.requestId ?? "unknown"}
              </p>
            )}
            {startCycleState.kind === "error" && (
              <p className="max-w-64 text-xs font-semibold text-red-700">
                Could not start cycle. Reference ID:{" "}
                {startCycleState.requestId ?? "unknown"}
              </p>
            )}
          </div>
        )}
      </div>
      <TreatmentObjectiveEditor
        value={t.clinical_objective}
        isSaving={objectiveState.kind === "saving"}
        onSave={(value) => void handleObjectiveSave(value)}
      />
      {objectiveState.kind === "error" && (
        <p className="mt-2 text-xs font-semibold text-red-700">
          Could not update treatment objective. Reference ID:{" "}
          {objectiveState.requestId ?? "unknown"}
        </p>
      )}
      {(isActive || terminateState.kind === "error") && (
        <div className="mt-6 border-t border-slate-100 pt-4">
          <div className="flex flex-col gap-3 rounded-lg border border-red-100 bg-red-50/40 p-4 md:flex-row md:items-center md:justify-between">
            <div>
              <p className="text-sm font-bold text-slate-900">
                Treatment control
              </p>
              <p className="mt-1 text-xs font-semibold leading-5 text-slate-600">
                End this monitoring cycle and stop future reminders and
                check-ins.
              </p>
              {terminateState.kind === "error" && (
                <p className="mt-2 text-xs font-semibold text-red-700">
                  Could not stop monitoring. Reference ID:{" "}
                  {terminateState.requestId ?? "unknown"}
                </p>
              )}
            </div>
            {terminateState.kind === "confirming" ? (
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => void handleTerminate()}
                  className="rounded-lg bg-red-700 px-3 py-2 text-xs font-bold text-white transition-colors hover:bg-red-800 cursor-pointer"
                >
                  Confirm stop
                </button>
                <button
                  type="button"
                  onClick={() => setTerminateState({ kind: "idle" })}
                  className="rounded-lg border border-red-200 bg-white px-3 py-2 text-xs font-bold text-red-700 transition-colors hover:bg-red-100 cursor-pointer"
                >
                  Keep monitoring
                </button>
              </div>
            ) : (
              isActive && (
                <button
                  type="button"
                  onClick={() => setTerminateState({ kind: "confirming" })}
                  disabled={terminateState.kind === "saving"}
                  className="inline-flex shrink-0 items-center justify-center gap-2 rounded-lg border border-red-200 bg-white px-4 py-2 text-sm font-bold text-red-700 transition-colors hover:border-red-700 hover:bg-red-700 hover:text-white disabled:cursor-wait disabled:border-red-100 disabled:text-red-300 disabled:hover:bg-white cursor-pointer"
                >
                  {terminateState.kind === "saving" ? (
                    <>
                      <Loader2 size={15} className="animate-spin" />
                      Stopping
                    </>
                  ) : (
                    "Stop monitoring"
                  )}
                </button>
              )
            )}
          </div>
        </div>
      )}
    </Section>
  );
}

function TreatmentObjectiveEditor({
  value,
  isSaving,
  onSave,
}: {
  value: string | null;
  isSaving: boolean;
  onSave: (value: string) => void;
}) {
  const [draft, setDraft] = useState(value ?? "");

  useEffect(() => {
    setDraft(value ?? "");
  }, [value]);

  const isDirty = draft.trim() !== (value ?? "").trim();

  return (
    <form
      className="mt-6"
      onSubmit={(event) => {
        event.preventDefault();
        if (isDirty && !isSaving) onSave(draft);
      }}
    >
      <label
        htmlFor="treatment-detail-objective"
        className="block text-[11px] font-bold uppercase tracking-wider text-slate-500"
      >
        Treatment Objective
      </label>
      <div className="mt-2 flex flex-col gap-2">
        <textarea
          id="treatment-detail-objective"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Add monitoring objective..."
          rows={3}
          className="min-w-0 flex-1 resize-none rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm leading-6 text-slate-900 focus:border-[#5548E8] focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#D9D5FB]"
        />
        <button
          type="submit"
          aria-label="Save objective"
          disabled={!isDirty || isSaving}
          className="inline-flex w-fit shrink-0 cursor-pointer items-center justify-center gap-2 self-end rounded-lg bg-slate-900 px-3.5 py-2 text-xs font-bold text-white transition-colors hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-400"
        >
          {isSaving ? (
            <>
              <Loader2 size={14} className="animate-spin" />
              Saving
            </>
          ) : (
            "Save Objective"
          )}
        </button>
      </div>
    </form>
  );
}

function TreatmentPlanChangedNotice() {
  return (
    <div className="mb-5 flex gap-3 rounded-lg border border-amber-200 bg-amber-50 p-4 text-amber-900">
      <AlertCircle size={18} className="mt-0.5 shrink-0" />
      <div>
        <p className="text-sm font-bold">Treatment plan changed</p>
        <p className="mt-1 text-sm font-semibold">
          Rerun analysis before monitoring can resume.
        </p>
      </div>
    </div>
  );
}

type CompletionReportState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ok"; report: CourseCompletionReport }
  | { kind: "error"; requestId: string | null };

type ArchiveState =
  | { kind: "idle" }
  | { kind: "saving" }
  | { kind: "error"; requestId: string | null };

function CompletionReportCard({
  treatment,
  onArchived,
}: {
  treatment: TreatmentDetail["treatment"];
  onArchived: (treatment: TreatmentView) => void;
}) {
  const [state, setState] = useState<CompletionReportState>({ kind: "idle" });
  const [archiveState, setArchiveState] = useState<ArchiveState>({
    kind: "idle",
  });
  const isCompleted = treatment.status === "completed";
  const archivedAt = treatment.archived_at ?? null;

  async function handleLoadReport(): Promise<void> {
    if (!isCompleted || state.kind === "loading") return;
    setState({ kind: "loading" });
    try {
      const report = await getCompletionReport(treatment.id);
      setState({ kind: "ok", report });
    } catch (err) {
      setState({
        kind: "error",
        requestId: err instanceof ApiError ? err.requestId : null,
      });
    }
  }

  async function handleArchive(): Promise<void> {
    if (!isCompleted || archivedAt || archiveState.kind === "saving") return;
    setArchiveState({ kind: "saving" });
    try {
      const archived = await archiveTreatment(treatment.id);
      onArchived(archived);
      setArchiveState({ kind: "idle" });
    } catch (err) {
      setArchiveState({
        kind: "error",
        requestId: err instanceof ApiError ? err.requestId : null,
      });
    }
  }

  return (
    <Section title="Completion Report" icon={<ClipboardList size={16} />}>
      {!isCompleted ? (
        <p className="text-sm font-semibold text-slate-500">
          Report available after course completion.
        </p>
      ) : (
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div>
              <p className="text-sm font-black text-slate-950">
                Course complete
              </p>
              <p className="mt-1 text-sm leading-6 text-slate-600">
                The report is count-based and excludes patient message text.
              </p>
              {archivedAt && (
                <p className="mt-2 inline-flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-bold text-slate-600">
                  <CheckCircle2 size={14} />
                  Archived {formatCreatedAt(archivedAt)}
                </p>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={handleLoadReport}
                disabled={state.kind === "loading"}
                className="inline-flex w-fit items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-bold text-slate-900 transition-colors hover:bg-slate-50 disabled:cursor-wait disabled:text-slate-400"
              >
                {state.kind === "loading" ? (
                  <>
                    <Loader2 size={15} className="animate-spin" />
                    Loading report
                  </>
                ) : (
                  "View Completion Report"
                )}
              </button>
              {!archivedAt && (
                <button
                  type="button"
                  onClick={handleArchive}
                  disabled={archiveState.kind === "saving"}
                  className="inline-flex w-fit items-center justify-center gap-2 rounded-lg border border-slate-300 bg-slate-50 px-4 py-2 text-sm font-bold text-slate-700 transition-colors hover:bg-white disabled:cursor-wait disabled:text-slate-400"
                >
                  {archiveState.kind === "saving" ? (
                    <>
                      <Loader2 size={15} className="animate-spin" />
                      Archiving
                    </>
                  ) : (
                    <>
                      <Archive size={15} />
                      Archive completed course
                    </>
                  )}
                </button>
              )}
            </div>
          </div>

          {state.kind === "error" && (
            <p className="text-sm font-semibold text-red-700">
              Could not load completion report. Reference ID:{" "}
              {state.requestId ?? "unknown"}
            </p>
          )}
          {archiveState.kind === "error" && (
            <p className="text-sm font-semibold text-red-700">
              Could not archive completed course. Reference ID:{" "}
              {archiveState.requestId ?? "unknown"}
            </p>
          )}
          {state.kind === "ok" && (
            <CompletionReportSummary report={state.report} />
          )}
        </div>
      )}
    </Section>
  );
}

function CompletionReportSummary({
  report,
}: {
  report: CourseCompletionReport;
}) {
  const taken = report.adherence.by_status.taken ?? 0;
  const missed = report.adherence.by_status.missed ?? 0;

  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
      <h4 className="text-sm font-black text-slate-950">
        Course Completion Report
      </h4>
      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <ReportMetric
          label="Medications"
          value={pluralize(report.medication_count, "medication")}
        />
        <ReportMetric label="Taken" value={`${taken} taken`} />
        <ReportMetric label="Missed" value={`${missed} missed`} />
        <ReportMetric
          label="Patient Updates"
          value={pluralize(
            report.patient_updates.total_count,
            "patient update",
          )}
        />
        <ReportMetric
          label="Triage"
          value={pluralize(report.triage.total_count, "triage item")}
        />
      </div>
    </div>
  );
}

function ReportMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3">
      <p className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
        {label}
      </p>
      <p className="mt-1 text-sm font-black text-slate-950 tabular-nums">
        {value}
      </p>
    </div>
  );
}

function pluralize(count: number, label: string): string {
  return `${count} ${label}${count === 1 ? "" : "s"}`;
}

function analysisReadyForCycle(analysis: TreatmentAnalysisRow | null): boolean {
  const completed = completedAnalysisForCycle(analysis);
  return completed?.status === "completed" && completed.result !== null;
}

function completedAnalysisForCycle(
  analysis: TreatmentAnalysisRow | null,
): TreatmentAnalysisRow | null {
  const completed =
    analysis?.status === "completed" ? analysis : analysis?.last_completed;
  return completed?.status === "completed" && completed.result !== null
    ? completed
    : null;
}

function treatmentPlanChangedAfterAnalysis(
  data: TreatmentDetail,
  activationAnalysis: ActivationAnalysisState,
): boolean {
  if (
    data.treatment.status === "pending" &&
    data.treatment.automation_mode === "paused" &&
    activationAnalysis.kind === "ok" &&
    !activationAnalysis.ready
  ) {
    return true;
  }
  if (activationAnalysis.kind !== "ok") return false;
  const latestDiscontinuedAt = latestMedicationDiscontinuedAt(data);
  if (!latestDiscontinuedAt) return false;
  if (!activationAnalysis.completedAt) return true;
  return (
    latestDiscontinuedAt.getTime() >
    new Date(activationAnalysis.completedAt).getTime()
  );
}

function latestMedicationDiscontinuedAt(data: TreatmentDetail): Date | null {
  const timestamps = data.medications
    .map((medication) =>
      medication.discontinued_at
        ? new Date(medication.discontinued_at).getTime()
        : null,
    )
    .filter(
      (timestamp): timestamp is number =>
        timestamp !== null && !Number.isNaN(timestamp),
    );
  if (timestamps.length === 0) return null;
  return new Date(Math.max(...timestamps));
}

function MedicationFormField({
  id,
  label,
  value,
  onChange,
  list,
  placeholder,
  required = false,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  list?: string;
  placeholder?: string;
  required?: boolean;
}) {
  return (
    <label htmlFor={id} className="block">
      <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
        {label}
      </span>
      <input
        id={id}
        list={list}
        placeholder={placeholder}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        required={required}
        className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-900 focus:border-[#5548E8] focus:outline-none focus:ring-2 focus:ring-[#D9D5FB]"
      />
    </label>
  );
}

type MedicationDiscontinueState =
  | { kind: "idle" }
  | { kind: "confirming"; medicationId: string }
  | { kind: "saving"; medicationId: string }
  | { kind: "error"; medicationId: string; requestId: string | null };

type MedicationAddState =
  | { kind: "closed" }
  | { kind: "editing" }
  | { kind: "saving" }
  | { kind: "error"; requestId: string | null };

type MedicationForm = {
  name: string;
  dosage: string;
  frequency: string;
  duration: string;
};

const EMPTY_MEDICATION_FORM: MedicationForm = {
  name: "",
  dosage: "",
  frequency: "",
  duration: "",
};

const FREQUENCY_SUGGESTIONS = [
  "Once Daily (QD)",
  "Twice Daily (BID)",
  "Three Times Daily (TID)",
  "Four Times Daily (QID)",
  "Every 4 Hours (Q4H)",
  "Every 6 Hours (Q6H)",
  "Every 8 Hours (Q8H)",
  "Every 12 Hours (Q12H)",
  "At Bedtime (QHS)",
  "As Needed (PRN)",
  "Once Weekly",
  "Once Monthly",
];

function MedicationsCard({
  data,
  onTreatmentDetailReloaded,
}: {
  data: TreatmentDetail;
  onTreatmentDetailReloaded: (detail: TreatmentDetail) => void;
}) {
  const [discontinueState, setDiscontinueState] =
    useState<MedicationDiscontinueState>({
      kind: "idle",
    });
  const [addState, setAddState] = useState<MedicationAddState>({
    kind: "closed",
  });
  const [form, setForm] = useState<MedicationForm>(EMPTY_MEDICATION_FORM);
  const canDiscontinue =
    data.treatment.status === "active" || data.treatment.status === "pending";
  const canAddMedication =
    data.treatment.status !== "completed" &&
    data.treatment.status !== "terminated";
  const canSaveMedication =
    form.name.trim() !== "" &&
    form.dosage.trim() !== "" &&
    form.frequency.trim() !== "" &&
    form.duration.trim() !== "" &&
    addState.kind !== "saving";

  async function handleDiscontinue(medicationId: string): Promise<void> {
    setDiscontinueState({ kind: "saving", medicationId });
    try {
      await discontinueMedication(data.treatment.id, medicationId);
      const detail = await getTreatment(data.treatment.id);
      onTreatmentDetailReloaded(detail);
      setDiscontinueState({ kind: "idle" });
    } catch (err) {
      setDiscontinueState({
        kind: "error",
        medicationId,
        requestId: err instanceof ApiError ? err.requestId : null,
      });
    }
  }

  async function handleAddMedication(
    event: FormEvent<HTMLFormElement>,
  ): Promise<void> {
    event.preventDefault();
    setAddState({ kind: "saving" });
    try {
      await addMedicationToTreatment(data.treatment.id, {
        name: form.name.trim(),
        dosage: form.dosage.trim(),
        frequency: form.frequency.trim(),
        duration: form.duration.trim(),
        // Per-medication objectives are not exposed in this workflow; the
        // treatment-level clinical objective remains the agent-facing intent.
        objective: null,
      });
      const detail = await getTreatment(data.treatment.id);
      onTreatmentDetailReloaded(detail);
      setForm(EMPTY_MEDICATION_FORM);
      setAddState({ kind: "closed" });
    } catch (err) {
      setAddState({
        kind: "error",
        requestId: err instanceof ApiError ? err.requestId : null,
      });
    }
  }

  const updateForm = (field: keyof MedicationForm, value: string) => {
    setForm((current) => ({ ...current, [field]: value }));
  };

  return (
    <Section title="Medications" icon={<Pill size={16} />}>
      <datalist id="frequency-suggestions">
        {FREQUENCY_SUGGESTIONS.map((suggestion) => (
          <option key={suggestion} value={suggestion} />
        ))}
      </datalist>
      {canAddMedication && (
        <div className="mb-4">
          {addState.kind === "closed" ? (
            <button
              type="button"
              onClick={() => setAddState({ kind: "editing" })}
              className="inline-flex cursor-pointer items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-bold text-slate-800 transition-colors hover:border-[#5548E8] hover:text-[#463AD4]"
            >
              <Plus size={15} />
              Add Medication
            </button>
          ) : (
            <form
              onSubmit={(event) => void handleAddMedication(event)}
              className="rounded-lg border border-slate-200 bg-slate-50 p-4"
            >
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                <MedicationFormField
                  id="new-medication-name"
                  label="Medication Name"
                  value={form.name}
                  onChange={(value) => updateForm("name", value)}
                  required
                />
                <MedicationFormField
                  id="new-medication-dosage"
                  label="Dosage Strength"
                  value={form.dosage}
                  onChange={(value) => updateForm("dosage", value)}
                  placeholder="e.g. 500mg"
                  required
                />
                <MedicationFormField
                  id="new-medication-frequency"
                  label="Frequency"
                  value={form.frequency}
                  onChange={(value) => updateForm("frequency", value)}
                  list="frequency-suggestions"
                  placeholder="e.g. Twice Daily (BID), Every 8 Hours, PRN"
                  required
                />
                <MedicationFormField
                  id="new-medication-duration"
                  label="Duration"
                  value={form.duration}
                  onChange={(value) => updateForm("duration", value)}
                  placeholder="e.g. 10 days"
                  required
                />
              </div>
              <div className="mt-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                <p className="text-xs font-semibold text-slate-500">
                  Saving a medication pauses monitoring until analysis is rerun.
                </p>
                <div className="flex justify-end gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      setAddState({ kind: "closed" });
                      setForm(EMPTY_MEDICATION_FORM);
                    }}
                    disabled={addState.kind === "saving"}
                    className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-bold text-slate-700 transition-colors hover:bg-slate-100 disabled:cursor-wait disabled:text-slate-400"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={!canSaveMedication}
                    className="rounded-lg bg-[#5548E8] px-3 py-2 text-sm font-bold text-white transition-colors hover:bg-[#463AD4] disabled:cursor-wait disabled:bg-slate-400"
                  >
                    {addState.kind === "saving" ? "Saving" : "Save Medication"}
                  </button>
                </div>
              </div>
              {addState.kind === "error" && (
                <p className="mt-3 text-xs font-semibold text-red-700">
                  Could not add medication. Reference ID:{" "}
                  {addState.requestId ?? "unknown"}
                </p>
              )}
            </form>
          )}
        </div>
      )}
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
              <th className="text-left py-2 pr-4">Status</th>
              <th className="text-right py-2 pl-4">Action</th>
            </tr>
          </thead>
          <tbody>
            {data.medications.map((m, i) => {
              const isDiscontinued = Boolean(m.discontinued_at);
              const isConfirming =
                discontinueState.kind === "confirming" &&
                discontinueState.medicationId === m.id;
              const isSaving =
                discontinueState.kind === "saving" &&
                discontinueState.medicationId === m.id;
              const errorForMedication =
                discontinueState.kind === "error" &&
                discontinueState.medicationId === m.id
                  ? discontinueState.requestId
                  : null;

              return (
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
                  <td className="py-2 pr-4">
                    {isDiscontinued ? (
                      <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-slate-600">
                        Discontinued
                      </span>
                    ) : (
                      <span className="rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-emerald-700">
                        Active
                      </span>
                    )}
                    {errorForMedication && (
                      <p className="mt-1 text-xs font-semibold text-red-700">
                        Could not discontinue. Reference ID:{" "}
                        {errorForMedication}
                      </p>
                    )}
                  </td>
                  <td className="py-2 pl-4 text-right">
                    {canDiscontinue &&
                      !isDiscontinued &&
                      (isConfirming ? (
                        <div className="flex justify-end gap-2">
                          <button
                            type="button"
                            onClick={() => void handleDiscontinue(m.id)}
                            className="rounded-lg bg-red-700 px-3 py-1.5 text-xs font-bold text-white transition-colors hover:bg-red-800 cursor-pointer"
                          >
                            Confirm
                          </button>
                          <button
                            type="button"
                            onClick={() =>
                              setDiscontinueState({ kind: "idle" })
                            }
                            className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-bold text-slate-700 transition-colors hover:bg-slate-50 cursor-pointer"
                          >
                            Keep
                          </button>
                        </div>
                      ) : (
                        <button
                          type="button"
                          onClick={() =>
                            setDiscontinueState({
                              kind: "confirming",
                              medicationId: m.id,
                            })
                          }
                          disabled={isSaving}
                          className="rounded-lg border border-red-200 bg-white px-3 py-1.5 text-xs font-bold text-red-700 transition-colors hover:border-red-700 hover:bg-red-700 hover:text-white disabled:cursor-wait disabled:text-red-300 cursor-pointer"
                        >
                          {isSaving ? "Discontinuing" : "Discontinue"}
                        </button>
                      ))}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Section>
  );
}
