import { Fragment, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  AlertCircle,
  CheckCircle2,
  Clock,
  Loader2,
  RefreshCw,
  ShieldAlert,
} from "lucide-react";

import { ApiError } from "../api/client";
import {
  listConversationMessages,
  type ConversationMessageView,
} from "../api/treatments";
import {
  approveTriageItem,
  listTriageItems,
  updateTriageItemStatus,
  type TriageItemView,
  type TriageReason,
  type TriageStatus,
} from "../api/triage";

const PAGE_SIZE = 50;

type FetchState =
  | { kind: "loading" }
  | { kind: "ok"; items: TriageItemView[] }
  | { kind: "error"; requestId: string | null };

type ActionError = {
  itemId: string;
  requestId: string | null;
};

type ConversationState =
  | { kind: "loading" }
  | { kind: "ok"; items: ConversationMessageView[] }
  | { kind: "error"; requestId: string | null };

const REASON_LABELS: Record<TriageReason, string> = {
  input_guard: "Incoming message safety review",
  referee: "Clinical draft review",
  output_guard: "Response safety review",
  adverse_event: "Possible adverse event",
  non_responsive: "Patient follow-up needed",
};

const STATUS_LABELS: Record<TriageStatus, string> = {
  open: "Open",
  acknowledged: "Acknowledged",
  resolved: "Resolved",
};

function formatCreatedAt(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function shortId(id: string): string {
  return id.slice(0, 8);
}

export default function TriageQueuePage() {
  const [state, setState] = useState<FetchState>({ kind: "loading" });
  const [actionItemId, setActionItemId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<ActionError | null>(null);
  const [expandedItemId, setExpandedItemId] = useState<string | null>(null);
  const [conversationByItem, setConversationByItem] = useState<
    Record<string, ConversationState>
  >({});

  useEffect(() => {
    let cancelled = false;

    listTriageItems({ limit: PAGE_SIZE, offset: 0 })
      .then((res) => {
        if (cancelled) return;
        setState({ kind: "ok", items: res.items });
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

  async function reloadQueue() {
    setState({ kind: "loading" });
    setActionError(null);
    try {
      const res = await listTriageItems({ limit: PAGE_SIZE, offset: 0 });
      setState({ kind: "ok", items: res.items });
    } catch (err: unknown) {
      setState({
        kind: "error",
        requestId: err instanceof ApiError ? err.requestId : null,
      });
    }
  }

  async function moveItem(itemId: string, status: TriageStatus) {
    setActionItemId(itemId);
    setActionError(null);
    try {
      const updated = await updateTriageItemStatus(itemId, status);
      setState((current) => {
        if (current.kind !== "ok") return current;
        return {
          kind: "ok",
          items: current.items.map((item) => (item.id === updated.id ? updated : item)),
        };
      });
    } catch (err: unknown) {
      setActionError({
        itemId,
        requestId: err instanceof ApiError ? err.requestId : null,
      });
    } finally {
      setActionItemId(null);
    }
  }

  async function approveItem(itemId: string) {
    setActionItemId(itemId);
    setActionError(null);
    try {
      const approval = await approveTriageItem(itemId);
      setState((current) => {
        if (current.kind !== "ok") return current;
        return {
          kind: "ok",
          items: current.items.map((item) =>
            item.id === approval.triage_item.id ? approval.triage_item : item,
          ),
        };
      });
      setConversationByItem((current) => {
        const existing = current[itemId];
        if (!existing || existing.kind !== "ok") return current;
        return {
          ...current,
          [itemId]: {
            kind: "ok",
            items: existing.items.map((message) =>
              message.id === approval.approved_message.id
                ? approval.approved_message
                : message,
            ),
          },
        };
      });
    } catch (err: unknown) {
      setActionError({
        itemId,
        requestId: err instanceof ApiError ? err.requestId : null,
      });
    } finally {
      setActionItemId(null);
    }
  }

  async function toggleConversation(item: TriageItemView) {
    if (expandedItemId === item.id) {
      setExpandedItemId(null);
      return;
    }

    setExpandedItemId(item.id);
    if (conversationByItem[item.id]) return;

    setConversationByItem((current) => ({
      ...current,
      [item.id]: { kind: "loading" },
    }));
    try {
      const res = await listConversationMessages(item.treatment_id, {
        limit: 100,
        offset: 0,
      });
      setConversationByItem((current) => ({
        ...current,
        [item.id]: { kind: "ok", items: res.items },
      }));
    } catch (err: unknown) {
      setConversationByItem((current) => ({
        ...current,
        [item.id]: {
          kind: "error",
          requestId: err instanceof ApiError ? err.requestId : null,
        },
      }));
    }
  }

  const items = state.kind === "ok" ? state.items : [];
  const stats = useMemo(() => buildStats(items), [items]);

  return (
    <div className="h-full overflow-y-auto p-8">
      <div className="flex flex-col gap-6">
        <Header onReload={reloadQueue} isReloading={state.kind === "loading"} />
        <StatsRow stats={stats} />
        {actionError && <ActionErrorCard error={actionError} />}
        {state.kind === "loading" && <LoadingCard />}
        {state.kind === "error" && (
          <ErrorCard requestId={state.requestId} onRetry={reloadQueue} />
        )}
        {state.kind === "ok" && state.items.length === 0 && <EmptyCard />}
        {state.kind === "ok" && state.items.length > 0 && (
          <TriageTable
            items={state.items}
            actionItemId={actionItemId}
            expandedItemId={expandedItemId}
            conversationByItem={conversationByItem}
            onApproveItem={approveItem}
            onMoveItem={moveItem}
            onToggleConversation={toggleConversation}
          />
        )}
      </div>
    </div>
  );
}

function buildStats(items: TriageItemView[]) {
  return {
    total: items.length,
    open: items.filter((item) => item.status === "open").length,
    acknowledged: items.filter((item) => item.status === "acknowledged").length,
    resolved: items.filter((item) => item.status === "resolved").length,
  };
}

function Header({
  onReload,
  isReloading,
}: {
  onReload: () => void;
  isReloading: boolean;
}) {
  return (
    <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 bg-red-50 text-red-700 rounded-xl flex items-center justify-center">
          <ShieldAlert size={20} />
        </div>
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-slate-900">Triage Queue</h2>
          <p className="text-sm text-slate-500">
            Safety-held patient conversations awaiting pharmacist review.
          </p>
        </div>
      </div>
      <button
        type="button"
        onClick={onReload}
        disabled={isReloading}
        className="inline-flex items-center justify-center gap-2 px-4 py-2 bg-white border border-slate-200 text-slate-700 rounded-xl font-bold hover:bg-slate-50 disabled:opacity-50 cursor-pointer"
      >
        {isReloading ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />}
        Refresh
      </button>
    </div>
  );
}

function StatsRow({
  stats,
}: {
  stats: { total: number; open: number; acknowledged: number; resolved: number };
}) {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
      <StatCard label="Total" value={stats.total} />
      <StatCard label="Open" value={stats.open} intent="red" />
      <StatCard label="Acknowledged" value={stats.acknowledged} intent="amber" />
      <StatCard label="Resolved" value={stats.resolved} intent="green" />
    </div>
  );
}

function StatCard({
  label,
  value,
  intent = "slate",
}: {
  label: string;
  value: number;
  intent?: "slate" | "red" | "amber" | "green";
}) {
  const colorClass = {
    slate: "text-slate-900",
    red: "text-red-700",
    amber: "text-amber-700",
    green: "text-emerald-700",
  }[intent];

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5">
      <p className="text-[11px] font-bold uppercase tracking-wider text-slate-500">{label}</p>
      <p className={`text-3xl font-bold mt-2 tabular-nums ${colorClass}`}>{value}</p>
    </div>
  );
}

function LoadingCard() {
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-10 flex items-center justify-center gap-3 text-slate-500">
      <Loader2 size={18} className="animate-spin" />
      <span>Loading triage queue...</span>
    </div>
  );
}

function EmptyCard() {
  return (
    <section className="bg-white border border-slate-200 rounded-xl p-8">
      <div className="max-w-2xl">
        <p className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
          No data available
        </p>
        <h3 className="text-xl font-bold text-slate-900 mt-2">
          No patients need review right now
        </h3>
        <p className="text-sm text-slate-500 mt-2">
          Safety-held replies, possible adverse events, and patient follow-up needs will appear
          here when the system needs a pharmacist to review them.
        </p>
      </div>
    </section>
  );
}

function ErrorCard({
  requestId,
  onRetry,
}: {
  requestId: string | null;
  onRetry: () => void;
}) {
  return (
    <div className="bg-white border border-amber-200 rounded-xl p-6 flex items-start justify-between gap-4">
      <div className="flex items-start gap-3">
        <AlertCircle size={20} className="text-amber-700 mt-0.5" />
        <div>
          <p className="font-bold text-slate-900">Triage queue is temporarily unavailable.</p>
          <p className="text-sm text-slate-500 mt-1">
            Please retry. Reference ID:{" "}
            <code className="text-slate-700">{requestId ?? "unknown"}</code>
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

function ActionErrorCard({ error }: { error: ActionError }) {
  return (
    <div className="bg-white border border-amber-200 rounded-xl p-4 flex items-start gap-3">
      <AlertCircle size={18} className="text-amber-700 mt-0.5" />
      <div>
        <p className="font-bold text-slate-900">Could not update review item.</p>
        <p className="text-sm text-slate-500">
          Item {shortId(error.itemId)} was not changed. Reference ID:{" "}
          <code className="text-slate-700">{error.requestId ?? "unknown"}</code>
        </p>
      </div>
    </div>
  );
}

function TriageTable({
  items,
  actionItemId,
  expandedItemId,
  conversationByItem,
  onApproveItem,
  onMoveItem,
  onToggleConversation,
}: {
  items: TriageItemView[];
  actionItemId: string | null;
  expandedItemId: string | null;
  conversationByItem: Record<string, ConversationState>;
  onApproveItem: (itemId: string) => Promise<void>;
  onMoveItem: (itemId: string, status: TriageStatus) => Promise<void>;
  onToggleConversation: (item: TriageItemView) => Promise<void>;
}) {
  return (
    <section className="bg-white border border-slate-200 rounded-xl overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-slate-50">
            <tr className="text-[11px] font-bold uppercase tracking-wider text-slate-500 border-b border-slate-200">
              <th className="text-left px-6 py-3">Created</th>
              <th className="text-left px-6 py-3">Review reason</th>
              <th className="text-left px-6 py-3">Treatment</th>
              <th className="text-left px-6 py-3">Status</th>
              <th className="text-right px-6 py-3">Action</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item, index) => (
              <Fragment key={item.id}>
                <tr
                  className={`border-b border-slate-100 ${
                    index % 2 === 1 ? "bg-slate-50/60" : "bg-white"
                  }`}
                >
                  <td className="px-6 py-4 text-slate-600 whitespace-nowrap">
                    <div className="flex items-center gap-2">
                      <Clock size={14} className="text-slate-400" />
                      {formatCreatedAt(item.created_at)}
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <p className="font-bold text-slate-900">{REASON_LABELS[item.reason]}</p>
                    <p className="text-xs text-slate-500 mt-1">Review ID {shortId(item.id)}</p>
                  </td>
                  <td className="px-6 py-4">
                    <Link
                      to={`/dashboard/treatments/${item.treatment_id}`}
                      className="font-mono font-bold text-blue-700 hover:underline"
                    >
                      {shortId(item.treatment_id)}
                    </Link>
                  </td>
                  <td className="px-6 py-4">
                    <StatusBadge status={item.status} />
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex flex-wrap justify-end gap-2">
                      <button
                        type="button"
                        onClick={() => void onToggleConversation(item)}
                        className="inline-flex min-w-36 items-center justify-center px-4 py-2 bg-white border border-slate-200 text-slate-700 rounded-xl font-bold hover:bg-slate-50 cursor-pointer"
                      >
                        {expandedItemId === item.id ? "Close review" : "Review item"}
                      </button>
                    </div>
                  </td>
                </tr>
                {expandedItemId === item.id && (
                  <tr key={`${item.id}-conversation`} className="bg-slate-50/80">
                    <td colSpan={5} className="px-6 py-5">
                      <ConversationPanel
                        item={item}
                        isBusy={actionItemId === item.id}
                        state={conversationByItem[item.id] ?? { kind: "loading" }}
                        onApproveItem={onApproveItem}
                        onMoveItem={onMoveItem}
                      />
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function ConversationPanel({
  item,
  isBusy,
  state,
  onApproveItem,
  onMoveItem,
}: {
  item: TriageItemView;
  isBusy: boolean;
  state: ConversationState;
  onApproveItem: (itemId: string) => Promise<void>;
  onMoveItem: (itemId: string, status: TriageStatus) => Promise<void>;
}) {
  if (state.kind === "loading") {
    return (
      <div className="flex items-center gap-2 text-sm text-slate-500">
        <Loader2 size={16} className="animate-spin" />
        Loading conversation context...
      </div>
    );
  }

  if (state.kind === "error") {
    return (
      <div className="flex items-start gap-2 text-sm text-amber-700">
        <AlertCircle size={16} className="mt-0.5" />
        <span>
          Could not load conversation context. Reference ID:{" "}
          <code>{state.requestId ?? "unknown"}</code>
        </span>
      </div>
    );
  }

  if (state.items.length === 0) {
    return <p className="text-sm text-slate-500">No conversation messages recorded yet.</p>;
  }

  const heldDraft = state.items.find((message) => message.id === item.conversation_message_id);
  const canApproveDraft = item.status === "acknowledged" && heldDraft?.status === "held_for_review";

  return (
    <div className="space-y-3">
      <div>
        <p className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
          Pharmacist review
        </p>
        <p className="text-xs text-slate-500 mt-1">
          Review the patient message and held assistant draft before changing queue status.
        </p>
      </div>
      <ReviewFocusPanel item={item} messages={state.items} />
      <div className="grid gap-3">
        {state.items.map((message) => (
          <ConversationMessageRow
            key={message.id}
            message={message}
            isHeldDraft={message.id === item.conversation_message_id}
          />
        ))}
      </div>
      <div className="flex items-center justify-end border-t border-slate-200 pt-4">
        <ReviewAction
          item={item}
          canApproveDraft={canApproveDraft}
          isBusy={isBusy}
          onApproveItem={onApproveItem}
          onMoveItem={onMoveItem}
        />
      </div>
    </div>
  );
}

function ReviewFocusPanel({
  item,
  messages,
}: {
  item: TriageItemView;
  messages: ConversationMessageView[];
}) {
  const heldDraft = messages.find((message) => message.id === item.conversation_message_id);
  const heldDraftIndex = heldDraft ? messages.findIndex((message) => message.id === heldDraft.id) : -1;
  const patientMessage =
    heldDraftIndex > 0
      ? [...messages.slice(0, heldDraftIndex)]
          .reverse()
          .find((message) => message.sender_type === "patient")
      : messages.find((message) => message.sender_type === "patient");

  return (
    <div className="grid gap-3 lg:grid-cols-2">
      <ReviewFocusCard
        label="Patient message"
        body={patientMessage?.body ?? "No patient message found for this review item."}
        createdAt={patientMessage?.created_at}
      />
      <ReviewFocusCard
        label="Held assistant draft"
        body={heldDraft?.body ?? "No held draft found for this review item."}
        createdAt={heldDraft?.created_at}
        intent="amber"
      />
    </div>
  );
}

function ReviewFocusCard({
  label,
  body,
  createdAt,
  intent = "slate",
}: {
  label: string;
  body: string;
  createdAt?: string;
  intent?: "slate" | "amber";
}) {
  const classes =
    intent === "amber"
      ? "border-amber-200 bg-amber-50/60"
      : "border-slate-200 bg-white";

  return (
    <div className={`rounded-xl border p-4 ${classes}`}>
      <div className="flex items-center justify-between gap-3">
        <p className="text-[11px] font-bold uppercase tracking-wider text-slate-500">{label}</p>
        {createdAt && <span className="text-xs text-slate-500">{formatCreatedAt(createdAt)}</span>}
      </div>
      <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-slate-800">{body}</p>
    </div>
  );
}

function ConversationMessageRow({
  message,
  isHeldDraft,
}: {
  message: ConversationMessageView;
  isHeldDraft: boolean;
}) {
  const senderLabel = {
    patient: "Patient",
    assistant: "Assistant",
    pharmacist: "Pharmacist",
    system: "System",
  }[message.sender_type];

  return (
    <div className="border border-slate-200 bg-white rounded-xl p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
            {senderLabel}
          </span>
          {isHeldDraft && message.status === "approved" && (
            <span className="inline-flex items-center rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-emerald-700">
              Approved
            </span>
          )}
          {isHeldDraft && message.status !== "approved" && (
            <span className="inline-flex items-center rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-amber-700">
              Held draft
            </span>
          )}
        </div>
        <span className="text-xs text-slate-500">{formatCreatedAt(message.created_at)}</span>
      </div>
      <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-slate-800">{message.body}</p>
      {message.safety_hold_reason && (
        <p className="mt-3 text-xs font-semibold text-amber-700">
          Hold reason: {REASON_LABELS[message.safety_hold_reason as TriageReason] ?? message.safety_hold_reason}
        </p>
      )}
    </div>
  );
}

function StatusBadge({ status }: { status: TriageStatus }) {
  const classes = {
    open: "bg-red-50 text-red-700 border-red-200",
    acknowledged: "bg-amber-50 text-amber-700 border-amber-200",
    resolved: "bg-emerald-50 text-emerald-700 border-emerald-200",
  }[status];

  return (
    <span
      className={`inline-flex items-center px-3 py-1 rounded-full border text-[11px] font-bold uppercase tracking-wider ${classes}`}
    >
      {STATUS_LABELS[status]}
    </span>
  );
}

function ReviewAction({
  item,
  canApproveDraft,
  isBusy,
  onApproveItem,
  onMoveItem,
}: {
  item: TriageItemView;
  canApproveDraft: boolean;
  isBusy: boolean;
  onApproveItem: (itemId: string) => Promise<void>;
  onMoveItem: (itemId: string, status: TriageStatus) => Promise<void>;
}) {
  if (item.status === "resolved") {
    return (
      <span className="inline-flex items-center gap-2 text-sm font-semibold text-slate-500">
        <CheckCircle2 size={16} className="text-emerald-700" />
        No action needed
      </span>
    );
  }

  const nextStatus: TriageStatus = item.status === "open" ? "acknowledged" : "resolved";
  const label = canApproveDraft
    ? "Approve draft"
    : item.status === "open"
      ? "Start review"
      : "Mark reviewed";
  const onClick = canApproveDraft
    ? () => void onApproveItem(item.id)
    : () => void onMoveItem(item.id, nextStatus);

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={isBusy}
      aria-label={`${label} item ${shortId(item.id)}`}
      className="inline-flex min-w-32 items-center justify-center gap-2 px-4 py-2 bg-slate-900 text-white rounded-xl font-bold hover:bg-slate-800 disabled:opacity-50 cursor-pointer"
    >
      {isBusy && <Loader2 size={16} className="animate-spin" />}
      {label}
    </button>
  );
}
