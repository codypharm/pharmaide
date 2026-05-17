import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type MouseEvent,
} from "react";
import {
  Activity,
  AlertCircle,
  Bot,
  CheckCircle2,
  Clock,
  Loader2,
  MessageSquare,
  Save,
  Search,
  Send,
  User,
} from "lucide-react";
import { Link, useOutletContext } from "react-router-dom";
import { toast } from "sonner";

import { ApiError } from "../api/client";
import {
  draftPatientReply,
  getTreatment,
  listPatientCheckIns,
  listConversationMessages,
  listTreatments,
  retryConversationMessageDelivery,
  sendPharmacistMessage,
  updateTreatmentClinicalObjective,
  updateTreatmentChatResponseMode,
  type ConversationMessageList,
  type ConversationMessageStatus,
  type ConversationMessageView,
  type PatientCheckInList,
  type PatientCheckInReportType,
  type PatientCheckInView,
  type TreatmentDetail,
  type TreatmentList,
  type TreatmentListItem,
  type TreatmentView,
} from "../api/treatments";
import {
  listTriageItems,
  type TriageItemView,
  type TriageReason,
} from "../api/triage";

type OutletContext = {
  isPrivacyMode: boolean;
};

type TreatmentState =
  | { kind: "loading" }
  | { kind: "ok"; items: TreatmentListItem[]; counts: TreatmentDirectoryCounts }
  | { kind: "error"; requestId: string | null };

type TreatmentDirectoryCounts = {
  active: number;
  completed: number;
  archived: number;
};

type ConversationState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ok"; items: ConversationMessageView[] }
  | { kind: "error"; requestId: string | null };

type TreatmentDetailState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ok"; data: TreatmentDetail }
  | { kind: "error"; requestId: string | null };

type PatientUpdatesState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ok"; items: PatientCheckInView[] }
  | { kind: "error"; requestId: string | null };

type PatientTreatmentGroup = {
  patientId: string;
  items: TreatmentListItem[];
};

type DirectoryFilter = "active" | "completed" | "archived";

const PAGE_SIZE = 50;
const CONVERSATION_REFRESH_INTERVAL_MS = 10_000;

const TRIAGE_REASON_LABELS: Record<TriageReason, string> = {
  input_guard: "Incoming message safety review",
  referee: "Clinical draft review",
  output_guard: "Response safety review",
  adverse_event: "Possible adverse event",
  emergency: "Urgent patient concern",
  side_effect: "Possible side effect",
  dose_change_request: "Dose-change request",
  diagnosis_request: "Diagnosis question",
  unclear_message: "Needs clarification",
  non_responsive: "Patient follow-up needed",
};

const PATIENT_UPDATE_LABELS: Record<PatientCheckInReportType, string> = {
  not_improving: "Not Improving",
  side_effect: "Side Effect",
  feeling_better: "Feeling Better",
  general_update: "General Update",
  missed_dose: "Missed Dose",
};

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function formatLastUpdated(date: Date | null): string {
  if (!date) return "Updating...";
  return `Updated ${date.toLocaleTimeString(undefined, {
    hour: "numeric",
    minute: "2-digit",
  })}`;
}

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

function patientAge(dob: string): string {
  const birth = new Date(dob);
  const now = new Date();
  let age = now.getFullYear() - birth.getFullYear();
  const monthDelta = now.getMonth() - birth.getMonth();
  if (monthDelta < 0 || (monthDelta === 0 && now.getDate() < birth.getDate())) {
    age -= 1;
  }
  return Number.isFinite(age) ? `${age}y` : "Age unavailable";
}

function statusLabel(status: string): string {
  return status.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function matchesDirectoryFilter(item: TreatmentListItem, filter: DirectoryFilter): boolean {
  const isArchived = Boolean(item.treatment.archived_at);
  if (filter === "archived") return isArchived;
  if (filter === "completed") return item.treatment.status === "completed" && !isArchived;
  return item.treatment.status !== "completed" && !isArchived;
}

function emptyDirectoryMessage(filter: DirectoryFilter): string {
  if (filter === "archived") return "No archived treatments";
  if (filter === "completed") return "No completed treatments";
  return "No active monitoring treatments";
}

function directoryFilterParams(filter: DirectoryFilter) {
  if (filter === "archived") {
    return { limit: PAGE_SIZE, offset: 0, archived: true };
  }
  if (filter === "completed") {
    return { limit: PAGE_SIZE, offset: 0, status: "completed" as const, archived: false };
  }
  return { limit: PAGE_SIZE, offset: 0, archived: false };
}

function countsFromTreatmentList(result: TreatmentList): TreatmentDirectoryCounts {
  return {
    active:
      result.active_count ??
      result.items.filter((item) => matchesDirectoryFilter(item, "active")).length,
    completed:
      result.completed_count ??
      result.items.filter((item) => matchesDirectoryFilter(item, "completed")).length,
    archived:
      result.archived_count ??
      result.items.filter((item) => matchesDirectoryFilter(item, "archived")).length,
  };
}

function groupTreatmentsByPatient(items: TreatmentListItem[]): PatientTreatmentGroup[] {
  const groups = new Map<string, PatientTreatmentGroup>();
  for (const item of items) {
    const group = groups.get(item.patient.id);
    if (group) {
      group.items.push(item);
    } else {
      groups.set(item.patient.id, { patientId: item.patient.id, items: [item] });
    }
  }
  return Array.from(groups.values());
}

export default function PatientManagementPage() {
  const { isPrivacyMode } = useOutletContext<OutletContext>();
  const [treatmentState, setTreatmentState] = useState<TreatmentState>({ kind: "loading" });
  const [conversationState, setConversationState] = useState<ConversationState>({ kind: "idle" });
  const [treatmentDetailState, setTreatmentDetailState] = useState<TreatmentDetailState>({
    kind: "idle",
  });
  const [patientUpdatesState, setPatientUpdatesState] = useState<PatientUpdatesState>({
    kind: "idle",
  });
  const [triageItems, setTriageItems] = useState<TriageItemView[]>([]);
  const [selectedTreatmentId, setSelectedTreatmentId] = useState<string | null>(null);
  const [directoryFilter, setDirectoryFilter] = useState<DirectoryFilter>("active");
  const [activeProfileTab, setActiveProfileTab] = useState<"patient" | "reasoning">("patient");
  const [searchQuery, setSearchQuery] = useState("");
  const [incomingMessage, setIncomingMessage] = useState("");
  const [pharmacistMessage, setPharmacistMessage] = useState("");
  const [isSubmittingMessage, setIsSubmittingMessage] = useState(false);
  const [isSendingPharmacistMessage, setIsSendingPharmacistMessage] = useState(false);
  const [isUpdatingChatMode, setIsUpdatingChatMode] = useState(false);
  const [isUpdatingObjective, setIsUpdatingObjective] = useState(false);
  const [retryingMessageId, setRetryingMessageId] = useState<string | null>(null);
  const [conversationLastUpdatedAt, setConversationLastUpdatedAt] = useState<Date | null>(null);

  useEffect(() => {
    let cancelled = false;
    setTreatmentState({ kind: "loading" });
    listTreatments(directoryFilterParams(directoryFilter))
      .then((res) => {
        if (cancelled) return;
        setTreatmentState({ kind: "ok", items: res.items, counts: countsFromTreatmentList(res) });
        setSelectedTreatmentId((current) =>
          res.items.some((item) => item.treatment.id === current)
            ? current
            : res.items[0]?.treatment.id ?? null,
        );
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setTreatmentState({
          kind: "error",
          requestId: err instanceof ApiError ? err.requestId : null,
        });
      });
    return () => {
      cancelled = true;
    };
  }, [directoryFilter]);

  useEffect(() => {
    let cancelled = false;
    listTriageItems({ limit: PAGE_SIZE, offset: 0 })
      .then((res) => {
        if (cancelled) return;
        setTriageItems(res.items);
      })
      .catch(() => {
        if (cancelled) return;
        setTriageItems([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!selectedTreatmentId) {
      setConversationState({ kind: "idle" });
      setTreatmentDetailState({ kind: "idle" });
      setPatientUpdatesState({ kind: "idle" });
      setConversationLastUpdatedAt(null);
      return;
    }

    let cancelled = false;
    setConversationState({ kind: "loading" });
    setTreatmentDetailState({ kind: "loading" });
    setPatientUpdatesState({ kind: "loading" });

    getTreatment(selectedTreatmentId)
      .then((res) => {
        if (cancelled) return;
        setTreatmentDetailState({ kind: "ok", data: res });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setTreatmentDetailState({
          kind: "error",
          requestId: err instanceof ApiError ? err.requestId : null,
        });
      });

    listConversationMessages(selectedTreatmentId, { limit: 100, offset: 0 })
      .then((res) => {
        if (cancelled) return;
        setConversationState({ kind: "ok", items: res.items });
        setConversationLastUpdatedAt(new Date());
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setConversationState({
          kind: "error",
          requestId: err instanceof ApiError ? err.requestId : null,
        });
      });

    listPatientCheckIns(selectedTreatmentId)
      .then((res) => {
        if (cancelled) return;
        setPatientUpdatesState({ kind: "ok", items: res.items });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setPatientUpdatesState({
          kind: "error",
          requestId: err instanceof ApiError ? err.requestId : null,
        });
      });

    return () => {
      cancelled = true;
    };
  }, [selectedTreatmentId]);

  useEffect(() => {
    if (!selectedTreatmentId) return;

    let cancelled = false;
    const refresh = async () => {
      try {
        const [conversation, triage, patientUpdates] = await Promise.all([
          listConversationMessages(selectedTreatmentId, { limit: 100, offset: 0 }),
          listTriageItems({ limit: PAGE_SIZE, offset: 0 }),
          listPatientCheckIns(selectedTreatmentId),
        ]);
        if (cancelled) return;
        setConversationState({ kind: "ok", items: conversation.items });
        setConversationLastUpdatedAt(new Date());
        setTriageItems(triage.items);
        setPatientUpdatesState({ kind: "ok", items: patientUpdates.items });
      } catch {
        // Keep the current view visible during transient polling failures.
      }
    };

    const intervalId = window.setInterval(refresh, CONVERSATION_REFRESH_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [selectedTreatmentId]);

  const treatments = treatmentState.kind === "ok" ? treatmentState.items : [];
  const filteredTreatments = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    const searchFiltered = !query
      ? treatments
      : treatments.filter((item) => {
          return (
            item.patient.name.toLowerCase().includes(query) ||
            item.patient.mrn.toLowerCase().includes(query) ||
            item.treatment.id.toLowerCase().includes(query)
          );
        });

    return searchFiltered.filter((item) => matchesDirectoryFilter(item, directoryFilter));
  }, [directoryFilter, searchQuery, treatments]);

  const groupedTreatments = useMemo(
    () => groupTreatmentsByPatient(filteredTreatments),
    [filteredTreatments],
  );
  const treatmentCounts =
    treatmentState.kind === "ok"
      ? treatmentState.counts
      : { active: 0, completed: 0, archived: 0 };

  useEffect(() => {
    if (treatmentState.kind !== "ok") return;
    if (filteredTreatments.length === 0) {
      setSelectedTreatmentId(null);
      return;
    }
    if (
      !selectedTreatmentId ||
      !filteredTreatments.some((item) => item.treatment.id === selectedTreatmentId)
    ) {
      setSelectedTreatmentId(filteredTreatments[0].treatment.id);
    }
  }, [filteredTreatments, selectedTreatmentId, treatmentState.kind]);

  const selectedTreatment =
    treatments.find((item) => item.treatment.id === selectedTreatmentId) ?? null;
  const selectedTreatmentTriageItems = useMemo(() => {
    if (!selectedTreatmentId) return [];
    return triageItems.filter(
      (item) =>
        item.treatment_id === selectedTreatmentId &&
        (item.status === "open" || item.status === "acknowledged"),
    );
  }, [selectedTreatmentId, triageItems]);

  async function refreshConversation(treatmentId: string): Promise<ConversationMessageList> {
    const res = await listConversationMessages(treatmentId, { limit: 100, offset: 0 });
    setConversationState({ kind: "ok", items: res.items });
    setConversationLastUpdatedAt(new Date());
    return res;
  }

  async function refreshPatientUpdates(treatmentId: string): Promise<PatientCheckInList> {
    const res = await listPatientCheckIns(treatmentId);
    setPatientUpdatesState({ kind: "ok", items: res.items });
    return res;
  }

  async function submitIncomingMessage() {
    if (!selectedTreatment || isSubmittingMessage) return;

    const patientMessage = incomingMessage.trim();
    if (!patientMessage) {
      toast.error("Enter an incoming WhatsApp message first");
      return;
    }

    setIsSubmittingMessage(true);
    try {
      const turn = await draftPatientReply(selectedTreatment.treatment.id, {
        patient_message: patientMessage,
      });
      setIncomingMessage("");
      await refreshConversation(selectedTreatment.treatment.id);
      await refreshPatientUpdates(selectedTreatment.treatment.id);
      await refreshTriageItems();

      if (turn.assistant_message.status === "held_for_review") {
        toast.success("Draft held for pharmacist review", {
          description: "The item is now available in the triage queue.",
        });
      } else {
        toast.success("Draft ready for patient", {
          description: "Safety checks allowed the generated response.",
        });
      }
    } catch (err: unknown) {
      const requestId = err instanceof ApiError ? err.requestId : null;
      toast.error("Could not process incoming message", {
        description: `Reference ID: ${requestId ?? "unknown"}`,
      });
    } finally {
      setIsSubmittingMessage(false);
    }
  }

  async function submitPharmacistMessage() {
    if (!selectedTreatment || isSendingPharmacistMessage) return;

    const message = pharmacistMessage.trim();
    if (!message) {
      toast.error("Enter a pharmacist WhatsApp message first");
      return;
    }

    setIsSendingPharmacistMessage(true);
    try {
      await sendPharmacistMessage(selectedTreatment.treatment.id, { message });
      setPharmacistMessage("");
      await refreshConversation(selectedTreatment.treatment.id);
      toast.success("Pharmacist message queued", {
        description: "It will be sent through the WhatsApp delivery workflow.",
      });
    } catch (err: unknown) {
      const requestId = err instanceof ApiError ? err.requestId : null;
      toast.error("Could not queue pharmacist message", {
        description: `Reference ID: ${requestId ?? "unknown"}`,
      });
    } finally {
      setIsSendingPharmacistMessage(false);
    }
  }

  async function updateChatResponseMode(mode: TreatmentView["chat_response_mode"]) {
    if (!selectedTreatment || isUpdatingChatMode) return;

    setIsUpdatingChatMode(true);
    try {
      const updated = await updateTreatmentChatResponseMode(selectedTreatment.treatment.id, {
        chat_response_mode: mode,
      });
      applyUpdatedTreatment(updated);
      toast.success(mode === "ai_active" ? "AI replies resumed" : "Pharmacist takeover active", {
        description:
          mode === "ai_active"
            ? "The agent can draft future patient replies for this treatment."
            : "Future patient reply drafts will wait while the pharmacist handles this thread.",
      });
    } catch (err: unknown) {
      const requestId = err instanceof ApiError ? err.requestId : null;
      toast.error("Could not update conversation control", {
        description: `Reference ID: ${requestId ?? "unknown"}`,
      });
    } finally {
      setIsUpdatingChatMode(false);
    }
  }

  async function updateClinicalObjective(value: string) {
    if (!selectedTreatment || isUpdatingObjective) return;

    const clinicalObjective = value.trim() || null;
    setIsUpdatingObjective(true);
    try {
      const updated = await updateTreatmentClinicalObjective(selectedTreatment.treatment.id, {
        clinical_objective: clinicalObjective,
      });
      applyUpdatedTreatment(updated);
      toast.success("Treatment objective updated", {
        description: "Monitoring context now reflects the saved objective.",
      });
    } catch (err: unknown) {
      const requestId = err instanceof ApiError ? err.requestId : null;
      toast.error("Could not update treatment objective", {
        description: `Reference ID: ${requestId ?? "unknown"}`,
      });
    } finally {
      setIsUpdatingObjective(false);
    }
  }

  async function retryMessageDelivery(messageId: string) {
    if (!selectedTreatment || retryingMessageId) return;

    setRetryingMessageId(messageId);
    try {
      await retryConversationMessageDelivery(selectedTreatment.treatment.id, messageId);
      await refreshConversation(selectedTreatment.treatment.id);
      toast.success("Message queued again", {
        description: "The delivery workflow will attempt to send it again.",
      });
    } catch (err: unknown) {
      const requestId = err instanceof ApiError ? err.requestId : null;
      toast.error("Could not retry message", {
        description: `Reference ID: ${requestId ?? "unknown"}`,
      });
    } finally {
      setRetryingMessageId(null);
    }
  }

  function applyUpdatedTreatment(updated: TreatmentView) {
    setTreatmentState((current) => {
      if (current.kind !== "ok") return current;
      return {
        kind: "ok",
        items: current.items.map((item) =>
          item.treatment.id === updated.id ? { ...item, treatment: updated } : item,
        ),
        counts: current.counts,
      };
    });
    setTreatmentDetailState((current) => {
      if (current.kind !== "ok" || current.data.treatment.id !== updated.id) return current;
      return { kind: "ok", data: { ...current.data, treatment: updated } };
    });
  }

  async function refreshTriageItems(): Promise<void> {
    try {
      const res = await listTriageItems({ limit: PAGE_SIZE, offset: 0 });
      setTriageItems(res.items);
    } catch {
      setTriageItems([]);
    }
  }

  return (
    <div className="flex h-full overflow-hidden bg-slate-50/50">
      <aside
        aria-label="Patient Directory"
        className="w-[420px] border-r border-slate-200 bg-white flex flex-col shrink-0 overflow-hidden"
      >
        <div className="p-6 border-b border-slate-100 flex flex-col gap-4">
          <div>
            <h2 className="text-xl font-bold text-slate-900 tracking-tight">Patient Directory</h2>
            <p className="text-sm text-slate-500 mt-1">
              Active monitoring and completed treatment courses.
            </p>
          </div>
          <div className="relative">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              placeholder="Search patients, MRN, or treatment..."
              className="w-full pl-9 pr-4 py-2 bg-slate-50 border border-slate-100 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-[#D9D5FB] focus:border-[#5548E8] transition-all"
            />
          </div>
          <div
            role="tablist"
            aria-label="Treatment status filter"
            className="inline-flex w-fit gap-1 rounded-lg border border-slate-200 bg-slate-100 p-1"
          >
            <DirectoryFilterTab
              label="Active"
              count={treatmentCounts.active}
              selected={directoryFilter === "active"}
              onClick={() => setDirectoryFilter("active")}
            />
            <DirectoryFilterTab
              label="Completed"
              count={treatmentCounts.completed}
              selected={directoryFilter === "completed"}
              onClick={() => setDirectoryFilter("completed")}
            />
            <DirectoryFilterTab
              label="Archived"
              count={treatmentCounts.archived}
              selected={directoryFilter === "archived"}
              onClick={() => setDirectoryFilter("archived")}
            />
          </div>
        </div>

        <div className="flex-1 overflow-y-auto">
          {treatmentState.kind === "loading" && <DirectoryLoading />}
          {treatmentState.kind === "error" && (
            <DirectoryError requestId={treatmentState.requestId} />
          )}
          {treatmentState.kind === "ok" && treatments.length > 0 && (
            <div className="divide-y divide-slate-100">
              {groupedTreatments.map((group) => (
                <PatientTreatmentGroup
                  key={group.patientId}
                  group={group}
                  selectedTreatmentId={selectedTreatmentId}
                  triageItems={triageItems}
                  isPrivacyMode={isPrivacyMode}
                  onSelectTreatment={setSelectedTreatmentId}
                  onOpenSafetyReview={(treatmentId) => {
                    setSelectedTreatmentId(treatmentId);
                    setActiveProfileTab("reasoning");
                  }}
                />
              ))}
              {filteredTreatments.length === 0 && (
                <div className="p-12 text-center">
                  <Search size={32} className="text-slate-200 mx-auto mb-4" />
                  <p className="text-sm font-bold text-slate-400 uppercase tracking-wider">
                    {emptyDirectoryMessage(directoryFilter)}
                  </p>
                </div>
              )}
            </div>
          )}
          {treatmentState.kind === "ok" && treatments.length === 0 && (
            <DirectoryFilterEmpty filter={directoryFilter} />
          )}
        </div>
      </aside>

      <main className="flex-1 flex flex-col overflow-hidden bg-white">
        {selectedTreatment ? (
          <>
            <PatientHeader item={selectedTreatment} isPrivacyMode={isPrivacyMode} />
            <div className="flex-1 flex overflow-hidden">
              <ClinicalWorkspace
                item={selectedTreatment}
                activeTriageItems={selectedTreatmentTriageItems}
                treatmentDetailState={treatmentDetailState}
                patientUpdatesState={patientUpdatesState}
                isUpdatingObjective={isUpdatingObjective}
                onUpdateClinicalObjective={updateClinicalObjective}
              />
              <InteractionLog
                activeProfileTab={activeProfileTab}
                conversationState={conversationState}
                conversationLastUpdatedAt={conversationLastUpdatedAt}
                activeTriageItems={selectedTreatmentTriageItems}
                incomingMessage={incomingMessage}
                pharmacistMessage={pharmacistMessage}
                chatResponseMode={selectedTreatment.treatment.chat_response_mode}
                isSubmittingMessage={isSubmittingMessage}
                isSendingPharmacistMessage={isSendingPharmacistMessage}
                isUpdatingChatMode={isUpdatingChatMode}
                retryingMessageId={retryingMessageId}
                onChangeIncomingMessage={setIncomingMessage}
                onChangePharmacistMessage={setPharmacistMessage}
                onSubmitIncomingMessage={submitIncomingMessage}
                onSubmitPharmacistMessage={submitPharmacistMessage}
                onUpdateChatResponseMode={updateChatResponseMode}
                onRetryMessageDelivery={retryMessageDelivery}
                onSetActiveProfileTab={setActiveProfileTab}
              />
            </div>
          </>
        ) : (
          <div className="h-full flex items-center justify-center text-sm text-slate-500">
            Select a treatment to review patient monitoring.
          </div>
        )}
      </main>
    </div>
  );
}

function DirectoryFilterTab({
  label,
  count,
  selected,
  onClick,
}: {
  label: string;
  count?: number;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={selected}
      aria-label={count !== undefined ? `${label} ${count}` : label}
      onClick={onClick}
      className={`inline-flex cursor-pointer items-center gap-2 rounded-md border px-3 py-2 text-xs font-bold transition-colors ${
        selected
          ? "border-slate-300 bg-white text-slate-950"
          : "border-transparent text-slate-500 hover:bg-white hover:text-slate-800"
      }`}
    >
      {label}
      {count !== undefined && (
        <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[10px] font-black tabular-nums text-slate-500">
          {count}
        </span>
      )}
    </button>
  );
}

function PatientTreatmentGroup({
  group,
  selectedTreatmentId,
  triageItems,
  isPrivacyMode,
  onSelectTreatment,
  onOpenSafetyReview,
}: {
  group: PatientTreatmentGroup;
  selectedTreatmentId: string | null;
  triageItems: TriageItemView[];
  isPrivacyMode: boolean;
  onSelectTreatment: (treatmentId: string) => void;
  onOpenSafetyReview: (treatmentId: string) => void;
}) {
  const patient = group.items[0].patient;
  const treatmentCountLabel = `${group.items.length} treatment${group.items.length === 1 ? "" : "s"}`;

  return (
    <section className="bg-white">
      <div className="px-4 pt-4 pb-2 flex items-center gap-3">
        <div className="h-9 w-9 rounded-lg border border-slate-200 bg-slate-50 flex items-center justify-center text-xs font-black text-slate-500">
          {initials(patient.name) || "P"}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-3">
            <p className={`truncate text-sm font-bold ${isPrivacyMode ? "blur-sm" : "text-slate-900"}`}>
              {patient.name}
            </p>
            <span className="shrink-0 rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[9px] font-black uppercase tracking-wider text-slate-500">
              {treatmentCountLabel}
            </span>
          </div>
          <p className="mt-0.5 text-[10px] font-medium text-slate-400">MRN {patient.mrn}</p>
        </div>
      </div>
      <div className="pb-2">
        {group.items.map((item) => (
          <TreatmentRow
            key={item.treatment.id}
            item={item}
            isSelected={selectedTreatmentId === item.treatment.id}
            activeFlagCount={activeFlagCountForTreatment(triageItems, item.treatment.id)}
            onSelect={() => onSelectTreatment(item.treatment.id)}
            onOpenSafetyReview={() => onOpenSafetyReview(item.treatment.id)}
          />
        ))}
      </div>
    </section>
  );
}

function activeFlagCountForTreatment(items: TriageItemView[], treatmentId: string): number {
  return items.filter(
    (item) =>
      item.treatment_id === treatmentId &&
      (item.status === "open" || item.status === "acknowledged"),
  ).length;
}

function DirectoryLoading() {
  return (
    <div className="p-8 flex items-center gap-2 text-sm text-slate-500">
      <Loader2 size={16} className="animate-spin" />
      Loading patients...
    </div>
  );
}

function DirectoryError({ requestId }: { requestId: string | null }) {
  return (
    <div className="m-4 rounded-xl border border-amber-200 bg-white p-4 text-sm text-slate-600">
      <div className="flex items-start gap-2">
        <AlertCircle size={16} className="text-amber-700 mt-0.5" />
        <div>
          <p className="font-bold text-slate-900">Could not load patient monitoring.</p>
          <p className="mt-1">
            Reference ID: <code>{requestId ?? "unknown"}</code>
          </p>
        </div>
      </div>
    </div>
  );
}

function DirectoryFilterEmpty({ filter }: { filter: DirectoryFilter }) {
  return (
    <div className="p-8 text-sm text-slate-500">
      <p className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
        No data available
      </p>
      <p className="mt-2 font-bold text-slate-900">{emptyDirectoryMessage(filter)}</p>
      <p className="mt-1">Switch tabs or create a treatment to continue monitoring.</p>
    </div>
  );
}

function TreatmentRow({
  item,
  isSelected,
  activeFlagCount,
  onSelect,
  onOpenSafetyReview,
}: {
  item: TreatmentListItem;
  isSelected: boolean;
  activeFlagCount: number;
  onSelect: () => void;
  onOpenSafetyReview: () => void;
}) {
  const medicationLabel =
    item.medication_count > 1
      ? `${item.first_medication_name ?? "Medication"} + ${item.medication_count - 1} more`
      : item.first_medication_name ?? "No medication name";
  const objectiveLabel = item.treatment.clinical_objective ?? "No objective recorded";
  const isCompleted = item.treatment.status === "completed";

  function handleRowSelect(event: MouseEvent<HTMLElement>) {
    if ((event.target as HTMLElement).closest("[data-flag-badge]")) {
      onOpenSafetyReview();
      return;
    }
    if ((event.target as HTMLElement).closest("[data-row-action]")) {
      return;
    }
    onSelect();
  }

  function handleRowKeyDown(event: KeyboardEvent<HTMLElement>) {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    onSelect();
  }

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={handleRowSelect}
      onKeyDown={handleRowKeyDown}
      className={`mx-4 mt-2 w-[calc(100%-2rem)] rounded-lg border p-3 text-left cursor-pointer transition-all hover:bg-slate-50/80 ${
        isSelected ? "border-[#D9D5FB] bg-[#F0EFFF]" : "border-slate-100 bg-white"
      }`}
    >
      <div className="flex justify-between items-start gap-4">
        <div className="flex flex-col min-w-0">
          <span className="truncate text-sm font-bold text-slate-900">
            {medicationLabel}
          </span>
          <span className="mt-0.5 truncate text-xs font-medium text-slate-500">
            {objectiveLabel}
          </span>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1">
          <span className="px-2 py-0.5 rounded text-[9px] font-black uppercase tracking-tighter bg-slate-50 text-slate-600 border border-slate-200">
            {statusLabel(item.treatment.status)}
          </span>
          {activeFlagCount > 0 && (
            <span
              data-flag-badge
              className="rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[9px] font-black uppercase tracking-wider text-amber-700"
            >
              {activeFlagCount} flag{activeFlagCount === 1 ? "" : "s"}
            </span>
          )}
        </div>
      </div>
      <div className="mt-3 flex items-center justify-between text-[10px] font-medium text-slate-400">
        <span className="font-mono uppercase tracking-widest">{item.treatment.id.slice(0, 8)}</span>
        <span>{formatDateTime(item.treatment.created_at)}</span>
      </div>
      <div className="mt-1 flex items-center justify-between text-[10px] font-medium text-slate-400">
        <span>Treatment</span>
        <span>{item.medication_count} med{item.medication_count === 1 ? "" : "s"}</span>
      </div>
      {isCompleted && (
        <div className="mt-3">
          <Link
            data-row-action
            to={`/dashboard/treatments/${item.treatment.id}`}
            className="inline-flex items-center rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-bold text-slate-900 transition-colors hover:bg-slate-50"
          >
            View report
          </Link>
        </div>
      )}
    </div>
  );
}

function PatientHeader({
  item,
  isPrivacyMode,
}: {
  item: TreatmentListItem;
  isPrivacyMode: boolean;
}) {
  const maskedName = `${item.patient.name.split(" ")[0] ?? "Patient"} ${
    item.patient.name.split(" ")[1]?.[0] ?? ""
  }.`;

  return (
    <div className="p-8 border-b border-slate-100 flex items-center justify-between shrink-0">
      <div className="flex flex-col">
        <div className="flex items-center gap-2 text-[10px] font-bold tracking-widest text-slate-400 uppercase mb-1">
          <span>Surveillance</span>
          <span className="text-[#5548E8]">{item.treatment.id.slice(0, 8)}</span>
        </div>
        <h1 className={`text-2xl font-bold text-slate-900 tracking-tight ${isPrivacyMode ? "blur-sm" : ""}`}>
          {isPrivacyMode ? maskedName : item.patient.name}, {patientAge(item.patient.dob)}
        </h1>
        <p className="text-sm text-slate-500">
          MRN: {item.patient.mrn} | First listed medication: {item.first_medication_name ?? "Not listed"}
        </p>
      </div>
      <div className="flex items-center gap-2">
        <Link
          to={`/dashboard/treatments/${item.treatment.id}`}
          className="inline-flex items-center justify-center rounded-lg border border-[#D9D5FB] bg-[#F0EFFF] px-3 py-2 text-xs font-bold text-[#463AD4] transition-colors hover:border-[#5548E8] hover:bg-[#5548E8] hover:!text-white"
        >
          Treatment Detail
        </Link>
        <div className="flex items-center gap-2 rounded-xl border border-slate-200 px-3 py-2 text-xs font-bold text-slate-600">
          <Clock size={14} />
          Created {formatDateTime(item.treatment.created_at)}
        </div>
      </div>
    </div>
  );
}

function ClinicalWorkspace({
  item,
  activeTriageItems,
  treatmentDetailState,
  patientUpdatesState,
  isUpdatingObjective,
  onUpdateClinicalObjective,
}: {
  item: TreatmentListItem;
  activeTriageItems: TriageItemView[];
  treatmentDetailState: TreatmentDetailState;
  patientUpdatesState: PatientUpdatesState;
  isUpdatingObjective: boolean;
  onUpdateClinicalObjective: (value: string) => void;
}) {
  return (
    <div className="flex-1 min-h-0 overflow-hidden p-8 flex flex-col gap-4">
      {activeTriageItems.length > 0 && (
        <NeedsReviewAlert items={activeTriageItems} />
      )}
      <section className="shrink-0 bg-white border border-slate-200 rounded-2xl p-5">
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex items-center gap-2">
              <Activity size={18} className="text-slate-400" />
              <h3 className="font-bold text-slate-900">Clinical Monitoring</h3>
            </div>
            <div className="flex flex-wrap gap-2">
              <ClinicalHeaderFact label="Status" value={statusLabel(item.treatment.status)} />
              <ClinicalHeaderFact
                label="Coverage"
                value={`${item.medication_count} medication${item.medication_count === 1 ? "" : "s"}`}
              />
            </div>
          </div>
          <ObjectiveEditor
            value={item.treatment.clinical_objective}
            isSaving={isUpdatingObjective}
            onSave={onUpdateClinicalObjective}
          />
        </div>
      </section>

      <MedicationsPanel state={treatmentDetailState} />

      <PatientUpdatesPanel state={patientUpdatesState} />
    </div>
  );
}

function ObjectiveEditor({
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
      className="mt-3"
      onSubmit={(event) => {
        event.preventDefault();
        if (isDirty && !isSaving) onSave(draft);
      }}
    >
      <label
        htmlFor="treatment-objective"
        className="block text-[10px] font-bold uppercase tracking-wider text-slate-500"
      >
        Treatment Objective
      </label>
      <div className="mt-2 flex flex-col gap-2 sm:flex-row sm:items-start">
        <textarea
          id="treatment-objective"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Add monitoring objective..."
          rows={3}
          className="min-w-0 flex-1 resize-none rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm leading-6 text-slate-800 focus:border-[#5548E8] focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#D9D5FB]"
        />
        <button
          type="submit"
          aria-label="Save objective"
          disabled={!isDirty || isSaving}
          className="inline-flex shrink-0 items-center justify-center gap-2 rounded-lg border border-slate-900 bg-slate-900 px-3.5 py-2 text-xs font-bold text-white transition-colors hover:bg-slate-800 disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-white disabled:text-slate-400 sm:self-start"
        >
          {isSaving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
          Save
        </button>
      </div>
    </form>
  );
}

function PatientUpdatesPanel({ state }: { state: PatientUpdatesState }) {
  if (state.kind === "idle" || state.kind === "loading") {
    return (
      <section className="bg-white border border-slate-200 rounded-2xl p-6">
        <h3 className="font-bold text-slate-900">Patient Updates</h3>
        <div className="mt-4 flex items-center gap-2 text-sm text-slate-500">
          <Loader2 size={16} className="animate-spin" />
          Loading patient updates...
        </div>
      </section>
    );
  }

  if (state.kind === "error") {
    return (
      <section className="bg-white border border-amber-200 rounded-2xl p-6">
        <h3 className="font-bold text-slate-900">Patient Updates</h3>
        <p className="mt-4 text-sm text-slate-600">
          Could not load patient updates. Reference ID: <code>{state.requestId ?? "unknown"}</code>
        </p>
      </section>
    );
  }

  if (state.items.length === 0) {
    return (
      <section className="bg-white border border-slate-200 rounded-2xl p-6">
        <h3 className="font-bold text-slate-900">Patient Updates</h3>
        <p className="mt-4 text-sm text-slate-500">No patient updates recorded.</p>
      </section>
    );
  }

  return (
    <section className="bg-white border border-slate-200 rounded-2xl p-6">
      <h3 className="font-bold text-slate-900">Patient Updates</h3>
      <div className="mt-4 divide-y divide-slate-100">
        {state.items.map((update) => (
          <article key={update.id} className="py-3 first:pt-0 last:pb-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-slate-700">
                {PATIENT_UPDATE_LABELS[update.report_type]}
              </span>
              <span className="rounded-full border border-slate-200 bg-white px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-slate-500">
                {statusLabel(update.source)}
              </span>
              <span className="text-[11px] font-medium text-slate-400">
                {formatDateTime(update.observed_at ?? update.created_at)}
              </span>
            </div>
            <p className="mt-2 text-sm leading-6 text-slate-700">{update.message}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

function NeedsReviewAlert({ items }: { items: TriageItemView[] }) {
  const firstItem = items[0];
  const reason = TRIAGE_REASON_LABELS[firstItem.reason];
  const itemCountLabel = `${items.length} active flag${items.length === 1 ? "" : "s"}`;

  return (
    <section className="rounded-2xl border border-amber-200 bg-amber-50 p-5">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex items-start gap-3">
          <AlertCircle size={18} className="mt-0.5 text-amber-700" />
          <div>
            <p className="text-[11px] font-bold uppercase tracking-wider text-amber-700">
              Needs pharmacist review
            </p>
            <p className="mt-1 text-sm font-bold text-slate-900">{reason}</p>
            <p className="mt-1 text-xs font-semibold text-slate-600">
              {itemCountLabel} from patient conversation
            </p>
          </div>
        </div>
        <Link
          to="/dashboard/triage"
          aria-label="Open triage queue"
          className="inline-flex shrink-0 items-center justify-center rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-bold text-slate-900 hover:bg-slate-50"
        >
          Open triage
        </Link>
      </div>
    </section>
  );
}

function MedicationsPanel({ state }: { state: TreatmentDetailState }) {
  if (state.kind === "idle" || state.kind === "loading") {
    return (
      <section className="min-h-0 flex-1 bg-white border border-slate-200 rounded-2xl p-6">
        <h3 className="font-bold text-slate-900">Medications</h3>
        <div className="mt-4 flex items-center gap-2 text-sm text-slate-500">
          <Loader2 size={16} className="animate-spin" />
          Loading medications...
        </div>
      </section>
    );
  }

  if (state.kind === "error") {
    return (
      <section className="min-h-0 flex-1 bg-white border border-amber-200 rounded-2xl p-6">
        <h3 className="font-bold text-slate-900">Medications</h3>
        <p className="mt-4 text-sm text-slate-600">
          Could not load medications. Reference ID: <code>{state.requestId ?? "unknown"}</code>
        </p>
      </section>
    );
  }

  if (state.data.medications.length === 0) {
    return (
      <section className="min-h-0 flex-1 bg-white border border-slate-200 rounded-2xl p-6">
        <h3 className="font-bold text-slate-900">Medications</h3>
        <p className="mt-4 text-sm text-slate-500">No medications recorded for this treatment.</p>
      </section>
    );
  }

  return (
    <section className="min-h-0 flex-1 bg-white border border-slate-200 rounded-2xl p-6 flex flex-col">
      <h3 className="shrink-0 font-bold text-slate-900">Medications</h3>
      <div className="mt-4 min-h-0 flex-1 overflow-auto">
        <table className="w-full min-w-[760px] table-fixed text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-[11px] font-bold uppercase tracking-wider text-slate-500">
              <th className="w-12 py-2 pr-4 text-left">#</th>
              <th className="w-[22%] py-2 pr-4 text-left">Name</th>
              <th className="py-2 pr-4 text-left">Dosage</th>
              <th className="py-2 pr-4 text-left">Frequency</th>
              <th className="py-2 pr-4 text-left">Duration</th>
              <th className="py-2 pr-4 text-left">Objective</th>
            </tr>
          </thead>
          <tbody>
            {state.data.medications.map((medication, index) => (
              <tr key={medication.id} className={index % 2 === 1 ? "bg-slate-50" : ""}>
                <td className="py-2 pr-4 tabular-nums text-slate-500">
                  {medication.ordinal + 1}
                </td>
                <td
                  className="py-2 pr-4 font-semibold leading-5 text-slate-900 whitespace-normal break-words"
                  title={medication.name}
                >
                  {medication.name}
                </td>
                <td className="py-2 pr-4 tabular-nums text-slate-700">{medication.dosage}</td>
                <td className="py-2 pr-4 text-slate-700">{medication.frequency}</td>
                <td className="py-2 pr-4 tabular-nums text-slate-700">{medication.duration}</td>
                <td className="py-2 pr-4 text-slate-500">{medication.objective ?? "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function ClinicalHeaderFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
      <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500">{label}</span>
      <span className="text-sm font-semibold text-slate-900">{value}</span>
    </div>
  );
}

function InteractionLog({
  activeProfileTab,
  conversationState,
  conversationLastUpdatedAt,
  activeTriageItems,
  incomingMessage,
  pharmacistMessage,
  chatResponseMode,
  isSubmittingMessage,
  isSendingPharmacistMessage,
  isUpdatingChatMode,
  retryingMessageId,
  onChangeIncomingMessage,
  onChangePharmacistMessage,
  onSubmitIncomingMessage,
  onSubmitPharmacistMessage,
  onUpdateChatResponseMode,
  onRetryMessageDelivery,
  onSetActiveProfileTab,
}: {
  activeProfileTab: "patient" | "reasoning";
  conversationState: ConversationState;
  conversationLastUpdatedAt: Date | null;
  activeTriageItems: TriageItemView[];
  incomingMessage: string;
  pharmacistMessage: string;
  chatResponseMode: TreatmentView["chat_response_mode"];
  isSubmittingMessage: boolean;
  isSendingPharmacistMessage: boolean;
  isUpdatingChatMode: boolean;
  retryingMessageId: string | null;
  onChangeIncomingMessage: (value: string) => void;
  onChangePharmacistMessage: (value: string) => void;
  onSubmitIncomingMessage: () => void;
  onSubmitPharmacistMessage: () => void;
  onUpdateChatResponseMode: (mode: TreatmentView["chat_response_mode"]) => void;
  onRetryMessageDelivery: (messageId: string) => void;
  onSetActiveProfileTab: (value: "patient" | "reasoning") => void;
}) {
  return (
    <aside className="w-[420px] border-l border-slate-200 bg-slate-50 flex flex-col shrink-0 overflow-hidden">
      <div className="p-4 border-b border-slate-200 bg-white flex items-center justify-between">
        <div className="flex items-center gap-2">
          <MessageSquare size={16} className="text-slate-400" />
          <h3 className="font-bold text-slate-900 text-sm">Interaction Log</h3>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-[9px] font-bold text-slate-400 uppercase tracking-wider">
            {formatLastUpdated(conversationLastUpdatedAt)}
          </span>
          <ChatModeSwitch
            mode={chatResponseMode}
            isUpdating={isUpdatingChatMode}
            onUpdateMode={onUpdateChatResponseMode}
          />
        </div>
      </div>

      <div className="p-1 bg-slate-200 mx-4 mt-4 rounded-lg flex gap-1">
        <button
          type="button"
          onClick={() => onSetActiveProfileTab("patient")}
          className={`flex-1 py-1.5 text-[10px] font-bold rounded-md transition-all cursor-pointer ${
            activeProfileTab === "patient"
              ? "bg-white text-slate-900 shadow-sm"
              : "text-slate-500 hover:text-slate-700"
          }`}
        >
          Patient Facing
        </button>
        <button
          type="button"
          onClick={() => onSetActiveProfileTab("reasoning")}
          className={`flex-1 py-1.5 text-[10px] font-bold rounded-md transition-all cursor-pointer ${
            activeProfileTab === "reasoning"
              ? "bg-white text-slate-900 shadow-sm"
              : "text-slate-500 hover:text-slate-700"
          }`}
        >
          Safety Review
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        {activeProfileTab === "patient" ? (
          <ConversationMessages
            state={conversationState}
            retryingMessageId={retryingMessageId}
            onRetryMessageDelivery={onRetryMessageDelivery}
          />
        ) : (
          <SafetyReviewPanel
            activeTriageItems={activeTriageItems}
            conversationState={conversationState}
          />
        )}
      </div>

      <div className="p-4 border-t border-slate-200 bg-white space-y-4">
        <div>
          <label
            htmlFor="pharmacist-whatsapp-message"
            className="mb-2 block text-[10px] font-bold uppercase tracking-wider text-slate-500"
          >
            Pharmacist WhatsApp Message
          </label>
          <div className="flex gap-2">
            <input
              id="pharmacist-whatsapp-message"
              value={pharmacistMessage}
              onChange={(event) => onChangePharmacistMessage(event.target.value)}
              placeholder="Type pharmacist reply..."
              className="flex-1 pl-4 pr-4 py-2 bg-white border border-slate-200 rounded-xl text-xs focus:ring-2 focus:ring-[#D9D5FB] transition-all"
            />
            <button
              type="button"
              onClick={onSubmitPharmacistMessage}
              disabled={isSendingPharmacistMessage}
              aria-label="Send pharmacist message"
              className="w-9 h-9 bg-slate-900 text-white rounded-lg flex items-center justify-center hover:bg-slate-800 transition-all cursor-pointer disabled:opacity-50"
            >
              {isSendingPharmacistMessage ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <Send size={14} />
              )}
            </button>
          </div>
        </div>
        <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50 p-3">
          <label
            htmlFor="test-patient-whatsapp-message"
            className="mb-1 block text-[10px] font-bold uppercase tracking-wider text-slate-500"
          >
            Test Patient WhatsApp Message
          </label>
          <p className="mb-2 text-[11px] font-medium leading-5 text-slate-500">
            Temporary simulator until WhatsApp webhooks are connected.
          </p>
          <div className="flex gap-2">
            <input
              id="test-patient-whatsapp-message"
              value={incomingMessage}
              onChange={(event) => onChangeIncomingMessage(event.target.value)}
              placeholder="Simulate patient reply..."
              className="flex-1 pl-4 pr-4 py-2 bg-white border border-slate-200 rounded-xl text-xs focus:ring-2 focus:ring-[#D9D5FB] transition-all"
            />
            <button
              type="button"
              onClick={onSubmitIncomingMessage}
              disabled={isSubmittingMessage}
              aria-label="Process test patient message"
              className="w-9 h-9 bg-slate-700 text-white rounded-lg flex items-center justify-center hover:bg-slate-800 transition-all cursor-pointer disabled:opacity-50"
            >
              {isSubmittingMessage ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
            </button>
          </div>
        </div>
      </div>
    </aside>
  );
}

function ChatModeSwitch({
  mode,
  isUpdating,
  onUpdateMode,
}: {
  mode: TreatmentView["chat_response_mode"];
  isUpdating: boolean;
  onUpdateMode: (mode: TreatmentView["chat_response_mode"]) => void;
}) {
  const isTakeover = mode === "pharmacist_takeover";

  return (
    <label className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-wider text-slate-600 cursor-pointer">
      <span className="w-24 text-right leading-4">
        {isTakeover ? "Pharmacist" : "Agent"}
      </span>
      <span className="relative inline-flex items-center">
        <input
          type="checkbox"
          role="switch"
          aria-label="Chat reply mode"
          className="peer sr-only"
          checked={isTakeover}
          onChange={(event) =>
            onUpdateMode(event.target.checked ? "pharmacist_takeover" : "ai_active")
          }
          disabled={isUpdating}
        />
        <span className="h-5 w-9 rounded-full bg-slate-300 transition-colors peer-checked:bg-slate-900 peer-disabled:opacity-60" />
        <span className="absolute left-0.5 h-4 w-4 rounded-full bg-white transition-transform peer-checked:translate-x-4" />
        {isUpdating && (
          <Loader2 size={12} className="absolute left-3.5 animate-spin text-slate-500" />
        )}
      </span>
    </label>
  );
}

function ConversationMessages({
  state,
  retryingMessageId,
  onRetryMessageDelivery,
}: {
  state: ConversationState;
  retryingMessageId: string | null;
  onRetryMessageDelivery: (messageId: string) => void;
}) {
  const latestMessageRef = useRef<HTMLDivElement | null>(null);
  const messageCount = state.kind === "ok" ? state.items.length : 0;

  useEffect(() => {
    if (messageCount === 0) return;
    latestMessageRef.current?.scrollIntoView({
      block: "end",
      behavior: "auto",
    });
  }, [messageCount]);

  if (state.kind === "idle") {
    return <p className="text-sm text-slate-500">Select a treatment to load messages.</p>;
  }

  if (state.kind === "loading") {
    return (
      <div className="flex items-center gap-2 text-sm text-slate-500">
        <Loader2 size={16} className="animate-spin" />
        Loading conversation...
      </div>
    );
  }

  if (state.kind === "error") {
    return (
      <div className="rounded-xl border border-amber-200 bg-white p-4 text-sm text-slate-600">
        <p className="font-bold text-slate-900">Could not load conversation.</p>
        <p className="mt-1">
          Reference ID: <code>{state.requestId ?? "unknown"}</code>
        </p>
      </div>
    );
  }

  if (state.items.length === 0) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-500">
        No conversation messages recorded yet.
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {state.items.map((message) => (
        <ConversationBubble
          key={message.id}
          message={message}
          isRetrying={retryingMessageId === message.id}
          onRetryMessageDelivery={onRetryMessageDelivery}
        />
      ))}
      <div ref={latestMessageRef} aria-hidden="true" />
    </div>
  );
}

function ConversationBubble({
  message,
  isRetrying,
  onRetryMessageDelivery,
}: {
  message: ConversationMessageView;
  isRetrying: boolean;
  onRetryMessageDelivery: (messageId: string) => void;
}) {
  const isPatient = message.sender_type === "patient";
  const isAssistant = message.sender_type === "assistant";
  const isPharmacist = message.sender_type === "pharmacist";
  const isOutbound = message.direction === "outbound";
  const messageSide = isOutbound ? "right" : "left";
  const bubbleClass = isPatient
    ? "bg-white text-slate-800 border border-slate-200 rounded-tl-none"
    : isPharmacist
      ? "bg-emerald-50 text-emerald-950 border border-emerald-100 rounded-tr-none"
    : "bg-slate-900 text-white rounded-tr-none";

  return (
    <div
      data-message-side={messageSide}
      className={`flex gap-3 ${isOutbound ? "flex-row-reverse" : ""}`}
    >
      <div
        className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${
          isPatient
            ? "bg-[#F0EFFF] text-[#463AD4]"
            : isPharmacist
              ? "bg-emerald-100 text-emerald-700"
              : "bg-slate-900 text-white"
        }`}
      >
        {isPatient || isPharmacist ? <User size={16} /> : <Bot size={16} />}
      </div>
      <div className="max-w-[85%]">
        <div className={`rounded-2xl p-3 ${bubbleClass}`}>
          <p className="text-sm leading-relaxed whitespace-pre-wrap">{message.body}</p>
        </div>
        <div className={`mt-1 flex items-center gap-2 text-[10px] text-slate-400 ${isOutbound ? "justify-end" : ""}`}>
          <span>{formatDateTime(message.created_at)}</span>
          {isAssistant && message.status === "held_for_review" && (
            <span className="inline-flex items-center gap-1 rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 font-bold uppercase tracking-wider text-amber-700">
              <CheckCircle2 size={10} />
              Held, not sent
            </span>
          )}
          {isOutbound && <DeliveryStatusBadge status={message.status} />}
          {isOutbound && message.status === "failed" && (
            <button
              type="button"
              onClick={() => onRetryMessageDelivery(message.id)}
              disabled={isRetrying}
              className="rounded-full border border-slate-200 bg-white px-2 py-0.5 font-bold uppercase tracking-wider text-slate-700 hover:bg-slate-50 disabled:opacity-50"
            >
              {isRetrying ? "Retrying" : "Retry send"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function DeliveryStatusBadge({ status }: { status: ConversationMessageStatus }) {
  const badge = deliveryStatusBadge(status);
  if (!badge) return null;

  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 font-bold uppercase tracking-wider ${badge.className}`}
    >
      <CheckCircle2 size={10} />
      {badge.label}
    </span>
  );
}

function deliveryStatusBadge(
  status: ConversationMessageStatus,
): { label: string; className: string } | null {
  if (status === "queued") {
    return {
      label: "Waiting to send",
      className: "border-slate-200 bg-slate-50 text-slate-600",
    };
  }
  if (status === "approved") {
    return {
      label: "Approved, not sent",
      className: "border-[#D9D5FB] bg-[#F0EFFF] text-[#463AD4]",
    };
  }
  if (status === "draft_ready") {
    return {
      label: "Ready, not sent",
      className: "border-slate-200 bg-slate-50 text-slate-600",
    };
  }
  if (status === "rejected") {
    return {
      label: "Canceled, not sent",
      className: "border-slate-300 bg-slate-100 text-slate-700",
    };
  }
  if (status === "sent") {
    return {
      label: "Sent",
      className: "border-emerald-200 bg-emerald-50 text-emerald-700",
    };
  }
  if (status === "failed") {
    return {
      label: "Send failed",
      className: "border-amber-200 bg-amber-50 text-amber-700",
    };
  }
  return null;
}

function SafetyReviewPanel({
  activeTriageItems,
  conversationState,
}: {
  activeTriageItems: TriageItemView[];
  conversationState: ConversationState;
}) {
  const messages = conversationState.kind === "ok" ? conversationState.items : [];

  if (activeTriageItems.length === 0) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-500">
        No active safety flags for this treatment.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-amber-200 bg-amber-50 p-3">
        <div className="flex items-center justify-between">
          <p className="text-[10px] font-bold uppercase tracking-wider text-amber-700">
            Active Safety Flags
          </p>
          <span className="rounded-full border border-amber-200 bg-white px-2 py-0.5 text-[9px] font-black uppercase tracking-wider text-amber-700">
            {activeTriageItems.length}
          </span>
        </div>
        <p className="mt-2 text-[11px] leading-5 text-amber-900">
          These items need pharmacist review before the patient-facing response is released.
        </p>
      </div>

      {activeTriageItems.map((item) => (
        <SafetyReviewFlagCard key={item.id} item={item} message={findMessage(messages, item)} />
      ))}
    </div>
  );
}

function SafetyReviewFlagCard({
  item,
  message,
}: {
  item: TriageItemView;
  message: ConversationMessageView | null;
}) {
  return (
    <article className="rounded-xl border border-slate-200 bg-white p-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-bold text-slate-900">{TRIAGE_REASON_LABELS[item.reason]}</p>
          <p className="mt-1 text-[10px] font-medium text-slate-400">
            Flagged {formatDateTime(item.created_at)}
          </p>
        </div>
        <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[9px] font-black uppercase tracking-wider text-slate-600">
          {statusLabel(item.status)}
        </span>
      </div>
      <div className="mt-3 rounded-lg border border-slate-100 bg-slate-50 p-3">
        <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">
          {message ? safetyReviewMessageLabel(message) : "Message context unavailable"}
        </p>
        {message ? (
          <p className="mt-2 text-xs leading-5 text-slate-700 whitespace-pre-wrap">{message.body}</p>
        ) : (
          <p className="mt-2 text-xs leading-5 text-slate-500">
            Open the Triage Queue for the full review context.
          </p>
        )}
      </div>
    </article>
  );
}

function findMessage(
  messages: ConversationMessageView[],
  item: TriageItemView,
): ConversationMessageView | null {
  if (!item.conversation_message_id) return null;
  return messages.find((message) => message.id === item.conversation_message_id) ?? null;
}

function safetyReviewMessageLabel(message: ConversationMessageView): string {
  if (message.status === "held_for_review") return "Held draft";
  if (message.status === "failed") return "Failed delivery";
  return statusLabel(message.sender_type);
}
