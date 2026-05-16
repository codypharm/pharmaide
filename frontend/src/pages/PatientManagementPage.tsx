import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertCircle,
  Bot,
  CheckCircle2,
  Clock,
  Loader2,
  MessageSquare,
  Search,
  Send,
  User,
  Zap,
} from "lucide-react";
import { Link, useOutletContext } from "react-router-dom";
import { toast } from "sonner";

import { ApiError } from "../api/client";
import {
  draftPatientReply,
  getTreatment,
  listConversationMessages,
  listTreatments,
  sendPharmacistMessage,
  type ConversationMessageList,
  type ConversationMessageView,
  type TreatmentDetail,
  type TreatmentListItem,
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
  | { kind: "ok"; items: TreatmentListItem[] }
  | { kind: "error"; requestId: string | null };

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

type PatientTreatmentGroup = {
  patientId: string;
  items: TreatmentListItem[];
};

const PAGE_SIZE = 50;

const TRIAGE_REASON_LABELS: Record<TriageReason, string> = {
  input_guard: "Incoming message safety review",
  referee: "Clinical draft review",
  output_guard: "Response safety review",
  adverse_event: "Possible adverse event",
  non_responsive: "Patient follow-up needed",
};

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
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
  const [triageItems, setTriageItems] = useState<TriageItemView[]>([]);
  const [selectedTreatmentId, setSelectedTreatmentId] = useState<string | null>(null);
  const [activeProfileTab, setActiveProfileTab] = useState<"patient" | "reasoning">("patient");
  const [searchQuery, setSearchQuery] = useState("");
  const [incomingMessage, setIncomingMessage] = useState("");
  const [pharmacistMessage, setPharmacistMessage] = useState("");
  const [isSubmittingMessage, setIsSubmittingMessage] = useState(false);
  const [isSendingPharmacistMessage, setIsSendingPharmacistMessage] = useState(false);

  useEffect(() => {
    let cancelled = false;
    listTreatments({ limit: PAGE_SIZE, offset: 0 })
      .then((res) => {
        if (cancelled) return;
        setTreatmentState({ kind: "ok", items: res.items });
        setSelectedTreatmentId((current) => current ?? res.items[0]?.treatment.id ?? null);
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
  }, []);

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
      return;
    }

    let cancelled = false;
    setConversationState({ kind: "loading" });
    setTreatmentDetailState({ kind: "loading" });

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
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setConversationState({
          kind: "error",
          requestId: err instanceof ApiError ? err.requestId : null,
        });
      });

    return () => {
      cancelled = true;
    };
  }, [selectedTreatmentId]);

  const treatments = treatmentState.kind === "ok" ? treatmentState.items : [];
  const filteredTreatments = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    if (!query) return treatments;
    return treatments.filter((item) => {
      return (
        item.patient.name.toLowerCase().includes(query) ||
        item.patient.mrn.toLowerCase().includes(query) ||
        item.treatment.id.toLowerCase().includes(query)
      );
    });
  }, [searchQuery, treatments]);

  const groupedTreatments = useMemo(
    () => groupTreatmentsByPatient(filteredTreatments),
    [filteredTreatments],
  );

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
      <aside className="w-[420px] border-r border-slate-200 bg-white flex flex-col shrink-0 overflow-hidden">
        <div className="p-6 border-b border-slate-100 flex flex-col gap-4">
          <div>
            <h2 className="text-xl font-bold text-slate-900 tracking-tight">Patient Directory</h2>
            <p className="text-sm text-slate-500 mt-1">Treatments with active monitoring context.</p>
          </div>
          <div className="relative">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              placeholder="Search patients, MRN, or treatment..."
              className="w-full pl-9 pr-4 py-2 bg-slate-50 border border-slate-100 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-100 focus:border-blue-500 transition-all"
            />
          </div>
        </div>

        <div className="flex-1 overflow-y-auto">
          {treatmentState.kind === "loading" && <DirectoryLoading />}
          {treatmentState.kind === "error" && (
            <DirectoryError requestId={treatmentState.requestId} />
          )}
          {treatmentState.kind === "ok" && treatments.length === 0 && <DirectoryEmpty />}
          {treatmentState.kind === "ok" && treatments.length > 0 && (
            <div className="divide-y divide-slate-100">
              {groupedTreatments.map((group) => (
                <PatientTreatmentGroup
                  key={group.patientId}
                  group={group}
                  selectedTreatmentId={selectedTreatmentId}
                  isPrivacyMode={isPrivacyMode}
                  onSelectTreatment={setSelectedTreatmentId}
                />
              ))}
              {filteredTreatments.length === 0 && (
                <div className="p-12 text-center">
                  <Search size={32} className="text-slate-200 mx-auto mb-4" />
                  <p className="text-sm font-bold text-slate-400 uppercase tracking-wider">
                    No patients found
                  </p>
                </div>
              )}
            </div>
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
              />
              <InteractionLog
                activeProfileTab={activeProfileTab}
                conversationState={conversationState}
                incomingMessage={incomingMessage}
                pharmacistMessage={pharmacistMessage}
                isSubmittingMessage={isSubmittingMessage}
                isSendingPharmacistMessage={isSendingPharmacistMessage}
                onChangeIncomingMessage={setIncomingMessage}
                onChangePharmacistMessage={setPharmacistMessage}
                onSubmitIncomingMessage={submitIncomingMessage}
                onSubmitPharmacistMessage={submitPharmacistMessage}
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

function PatientTreatmentGroup({
  group,
  selectedTreatmentId,
  isPrivacyMode,
  onSelectTreatment,
}: {
  group: PatientTreatmentGroup;
  selectedTreatmentId: string | null;
  isPrivacyMode: boolean;
  onSelectTreatment: (treatmentId: string) => void;
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
            onSelect={() => onSelectTreatment(item.treatment.id)}
          />
        ))}
      </div>
    </section>
  );
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

function DirectoryEmpty() {
  return (
    <div className="p-8 text-sm text-slate-500">
      <p className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
        No data available
      </p>
      <p className="mt-2 font-bold text-slate-900">No treatments registered</p>
      <p className="mt-1">Create a treatment before patient monitoring can start.</p>
    </div>
  );
}

function TreatmentRow({
  item,
  isSelected,
  onSelect,
}: {
  item: TreatmentListItem;
  isSelected: boolean;
  onSelect: () => void;
}) {
  const medicationLabel =
    item.medication_count > 1
      ? `${item.first_medication_name ?? "Medication"} + ${item.medication_count - 1} more`
      : item.first_medication_name ?? "No medication name";
  const objectiveLabel = item.treatment.clinical_objective ?? "No objective recorded";

  return (
    <button
      type="button"
      onClick={onSelect}
      className={`mx-4 mt-2 w-[calc(100%-2rem)] rounded-lg border p-3 text-left cursor-pointer transition-all hover:bg-slate-50/80 ${
        isSelected ? "border-blue-200 bg-blue-50/60" : "border-slate-100 bg-white"
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
        <span className="px-2 py-0.5 rounded text-[9px] font-black uppercase tracking-tighter bg-slate-50 text-slate-600 border border-slate-200">
          {statusLabel(item.treatment.status)}
        </span>
      </div>
      <div className="mt-3 flex items-center justify-between text-[10px] font-medium text-slate-400">
        <span className="font-mono uppercase tracking-widest">{item.treatment.id.slice(0, 8)}</span>
        <span>{formatDateTime(item.treatment.created_at)}</span>
      </div>
      <div className="mt-1 flex items-center justify-between text-[10px] font-medium text-slate-400">
        <span>Treatment</span>
        <span>{item.medication_count} med{item.medication_count === 1 ? "" : "s"}</span>
      </div>
    </button>
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
          <span className="text-blue-600">{item.treatment.id.slice(0, 8)}</span>
        </div>
        <h1 className={`text-2xl font-bold text-slate-900 tracking-tight ${isPrivacyMode ? "blur-sm" : ""}`}>
          {isPrivacyMode ? maskedName : item.patient.name}, {patientAge(item.patient.dob)}
        </h1>
        <p className="text-sm text-slate-500">
          MRN: {item.patient.mrn} | First listed medication: {item.first_medication_name ?? "Not listed"}
        </p>
      </div>
      <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-bold text-slate-600">
        <Clock size={14} />
        Created {formatDateTime(item.treatment.created_at)}
      </div>
    </div>
  );
}

function ClinicalWorkspace({
  item,
  activeTriageItems,
  treatmentDetailState,
}: {
  item: TreatmentListItem;
  activeTriageItems: TriageItemView[];
  treatmentDetailState: TreatmentDetailState;
}) {
  return (
    <div className="flex-1 overflow-y-auto p-8 flex flex-col gap-6">
      {activeTriageItems.length > 0 && (
        <NeedsReviewAlert items={activeTriageItems} />
      )}
      <section className="bg-white border border-slate-200 rounded-2xl p-6">
        <div className="flex items-center gap-2 mb-5">
          <Activity size={18} className="text-slate-400" />
          <h3 className="font-bold text-slate-900">Clinical Monitoring</h3>
        </div>
        <div className="grid gap-4">
          <ClinicalFact label="Treatment status" value={statusLabel(item.treatment.status)} />
          <ClinicalFact
            label="Medication coverage"
            value={`${item.medication_count} medication${item.medication_count === 1 ? "" : "s"}`}
          />
          <ClinicalFact
            label="Current objective"
            value={item.treatment.clinical_objective ?? "No objective recorded"}
          />
        </div>
      </section>

      <MedicationsPanel state={treatmentDetailState} />

      <section className="bg-white border border-slate-200 rounded-2xl p-6">
        <div className="flex items-center gap-2 mb-5">
          <Zap size={18} className="text-slate-400" />
          <h3 className="font-bold text-slate-900">Agent Direction</h3>
        </div>
        <p className="text-sm leading-6 text-slate-600">
          Incoming WhatsApp messages are processed through the patient-reply draft endpoint.
          Drafts that fail safety review are held and appear in the Triage Queue.
        </p>
      </section>
    </div>
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
          className="inline-flex items-center justify-center rounded-xl bg-slate-900 px-4 py-2 text-sm font-bold text-white hover:bg-slate-800"
        >
          Open Triage Queue
        </Link>
      </div>
    </section>
  );
}

function MedicationsPanel({ state }: { state: TreatmentDetailState }) {
  if (state.kind === "idle" || state.kind === "loading") {
    return (
      <section className="bg-white border border-slate-200 rounded-2xl p-6">
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
      <section className="bg-white border border-amber-200 rounded-2xl p-6">
        <h3 className="font-bold text-slate-900">Medications</h3>
        <p className="mt-4 text-sm text-slate-600">
          Could not load medications. Reference ID: <code>{state.requestId ?? "unknown"}</code>
        </p>
      </section>
    );
  }

  if (state.data.medications.length === 0) {
    return (
      <section className="bg-white border border-slate-200 rounded-2xl p-6">
        <h3 className="font-bold text-slate-900">Medications</h3>
        <p className="mt-4 text-sm text-slate-500">No medications recorded for this treatment.</p>
      </section>
    );
  }

  return (
    <section className="bg-white border border-slate-200 rounded-2xl p-6">
      <h3 className="font-bold text-slate-900">Medications</h3>
      <div className="mt-4 overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-[11px] font-bold uppercase tracking-wider text-slate-500">
              <th className="w-12 py-2 pr-4 text-left">#</th>
              <th className="py-2 pr-4 text-left">Name</th>
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
                <td className="py-2 pr-4 font-semibold text-slate-900">{medication.name}</td>
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

function ClinicalFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-slate-100 bg-slate-50 p-4">
      <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">{label}</p>
      <p className="mt-1 text-sm font-semibold text-slate-800">{value}</p>
    </div>
  );
}

function InteractionLog({
  activeProfileTab,
  conversationState,
  incomingMessage,
  pharmacistMessage,
  isSubmittingMessage,
  isSendingPharmacistMessage,
  onChangeIncomingMessage,
  onChangePharmacistMessage,
  onSubmitIncomingMessage,
  onSubmitPharmacistMessage,
  onSetActiveProfileTab,
}: {
  activeProfileTab: "patient" | "reasoning";
  conversationState: ConversationState;
  incomingMessage: string;
  pharmacistMessage: string;
  isSubmittingMessage: boolean;
  isSendingPharmacistMessage: boolean;
  onChangeIncomingMessage: (value: string) => void;
  onChangePharmacistMessage: (value: string) => void;
  onSubmitIncomingMessage: () => void;
  onSubmitPharmacistMessage: () => void;
  onSetActiveProfileTab: (value: "patient" | "reasoning") => void;
}) {
  return (
    <aside className="w-[420px] border-l border-slate-200 bg-slate-50 flex flex-col shrink-0 overflow-hidden">
      <div className="p-4 border-b border-slate-200 bg-white flex items-center justify-between">
        <div className="flex items-center gap-2">
          <MessageSquare size={16} className="text-slate-400" />
          <h3 className="font-bold text-slate-900 text-sm">Interaction Log</h3>
        </div>
        <span className="text-[9px] font-bold text-slate-400 uppercase tracking-wider">
          WhatsApp
        </span>
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
          Agent Reasoning
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        {activeProfileTab === "patient" ? (
          <ConversationMessages state={conversationState} />
        ) : (
          <ReasoningPlaceholder />
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
              className="flex-1 pl-4 pr-4 py-2 bg-white border border-slate-200 rounded-xl text-xs focus:ring-2 focus:ring-blue-100 transition-all"
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
        <label
          htmlFor="incoming-whatsapp-message"
          className="mb-2 block text-[10px] font-bold uppercase tracking-wider text-slate-500"
        >
          Incoming WhatsApp Message
        </label>
        <div className="flex gap-2">
          <input
            id="incoming-whatsapp-message"
            value={incomingMessage}
            onChange={(event) => onChangeIncomingMessage(event.target.value)}
            placeholder="e.g. I feel dizzy after taking it."
            className="flex-1 pl-4 pr-4 py-2 bg-white border border-slate-200 rounded-xl text-xs focus:ring-2 focus:ring-blue-100 transition-all"
          />
          <button
            type="button"
            onClick={onSubmitIncomingMessage}
            disabled={isSubmittingMessage}
            aria-label="Process incoming message"
            className="w-9 h-9 bg-slate-900 text-white rounded-lg flex items-center justify-center hover:bg-slate-800 transition-all cursor-pointer disabled:opacity-50"
          >
            {isSubmittingMessage ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
          </button>
        </div>
      </div>
    </aside>
  );
}

function ConversationMessages({ state }: { state: ConversationState }) {
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
        <ConversationBubble key={message.id} message={message} />
      ))}
    </div>
  );
}

function ConversationBubble({ message }: { message: ConversationMessageView }) {
  const isPatient = message.sender_type === "patient";
  const isAssistant = message.sender_type === "assistant";
  const isPharmacist = message.sender_type === "pharmacist";
  const bubbleClass = isPatient
    ? "bg-blue-600 text-white rounded-tr-none"
    : isPharmacist
      ? "bg-emerald-50 text-emerald-950 border border-emerald-100 rounded-tl-none"
    : "bg-slate-100 text-slate-700 rounded-tl-none";

  return (
    <div className={`flex gap-3 ${isPatient ? "flex-row-reverse" : ""}`}>
      <div
        className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${
          isPatient
            ? "bg-blue-100 text-blue-700"
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
        <div className={`mt-1 flex items-center gap-2 text-[10px] text-slate-400 ${isPatient ? "justify-end" : ""}`}>
          <span>{formatDateTime(message.created_at)}</span>
          {isAssistant && message.status === "held_for_review" && (
            <span className="inline-flex items-center gap-1 rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 font-bold uppercase tracking-wider text-amber-700">
              <CheckCircle2 size={10} />
              Held
            </span>
          )}
          {isPharmacist && message.status === "queued" && (
            <span className="inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 font-bold uppercase tracking-wider text-emerald-700">
              <CheckCircle2 size={10} />
              Queued
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

function ReasoningPlaceholder() {
  return (
    <div className="space-y-4">
      <div className="p-3 border border-slate-100 rounded-xl bg-slate-50/50 space-y-1.5">
        <div className="flex items-center justify-between">
          <span className="text-[10px] font-mono text-slate-400">Live</span>
          <span className="px-1.5 py-0.5 bg-slate-200 text-slate-600 text-[8px] font-bold uppercase rounded tracking-wider">
            Safety
          </span>
        </div>
        <p className="text-xs text-slate-700 font-medium">
          Patient-facing drafts are routed through input guard, clinical referee, and output guard.
        </p>
      </div>
      <div className="p-3 bg-blue-50 border border-blue-100 rounded-xl">
        <p className="text-[10px] font-bold text-blue-600 uppercase tracking-widest mb-2">
          Triage handoff
        </p>
        <p className="text-[11px] text-blue-800 leading-relaxed">
          Held drafts are visible in the Triage Queue with their conversation context.
        </p>
      </div>
    </div>
  );
}
