import {
  AlertCircle,
  Bot,
  CheckCircle2,
  Download,
  Loader2,
  RefreshCw,
  Search,
  ShieldCheck,
  User,
  Zap,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { listAuditLogEntries, type AuditLogEntryView } from "../api/audits";
import { ApiError } from "../api/client";

const PAGE_SIZE = 50;
const ACTOR_FILTERS = ["All", "Agent", "Human", "System"] as const;

type ActorFilter = (typeof ACTOR_FILTERS)[number];

type AuditExactFilters = {
  event_type: string;
  resource_type: string;
  actor_id: string;
};

const EMPTY_EXACT_FILTERS: AuditExactFilters = {
  event_type: "",
  resource_type: "",
  actor_id: "",
};

type FetchState =
  | { kind: "loading" }
  | { kind: "ok"; items: AuditLogEntryView[]; hasMore: boolean }
  | { kind: "error"; requestId: string | null };

export default function SystemAuditsPage() {
  const [searchQuery, setSearchQuery] = useState("");
  const [actorFilter, setActorFilter] = useState<ActorFilter>("All");
  const [draftExactFilters, setDraftExactFilters] =
    useState<AuditExactFilters>(EMPTY_EXACT_FILTERS);
  const [appliedExactFilters, setAppliedExactFilters] =
    useState<AuditExactFilters>(EMPTY_EXACT_FILTERS);
  const [state, setState] = useState<FetchState>({ kind: "loading" });
  const [isLoadingMore, setIsLoadingMore] = useState(false);

  const refresh = useCallback(async () => {
    setState({ kind: "loading" });
    try {
      const result = await listAuditLogEntries({
        limit: PAGE_SIZE,
        offset: 0,
        ...requestFilters(appliedExactFilters),
      });
      setState({
        kind: "ok",
        items: result.items,
        hasMore: result.items.length === PAGE_SIZE,
      });
    } catch (err) {
      setState({ kind: "error", requestId: auditRequestId(err) });
    }
  }, [appliedExactFilters]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const filteredLogs = useMemo(() => {
    if (state.kind !== "ok") return [];
    return state.items.filter((log) => {
      const query = searchQuery.trim().toLowerCase();
      const matchesSearch =
        !query ||
        [
          log.id,
          log.event_type,
          log.resource_type,
          log.resource_id,
          actorLabel(log),
          payloadSummary(log.payload),
        ]
          .join(" ")
          .toLowerCase()
          .includes(query);
      const matchesActor = actorFilter === "All" || actorLabel(log) === actorFilter;
      return matchesSearch && matchesActor;
    });
  }, [actorFilter, searchQuery, state]);

  async function loadOlderLogs() {
    if (state.kind !== "ok" || isLoadingMore || !state.hasMore) return;
    setIsLoadingMore(true);
    try {
      const result = await listAuditLogEntries({
        limit: PAGE_SIZE,
        offset: state.items.length,
        ...requestFilters(appliedExactFilters),
      });
      setState({
        kind: "ok",
        items: [...state.items, ...result.items],
        hasMore: result.items.length === PAGE_SIZE,
      });
    } catch (err) {
      setState({ kind: "error", requestId: auditRequestId(err) });
    } finally {
      setIsLoadingMore(false);
    }
  }

  function applyExactFilters() {
    setAppliedExactFilters(normaliseExactFilters(draftExactFilters));
  }

  function clearExactFilters() {
    setDraftExactFilters(EMPTY_EXACT_FILTERS);
    setAppliedExactFilters(EMPTY_EXACT_FILTERS);
  }

  function exportVisibleLogs() {
    const rows = filteredLogs.map((log) => ({
      id: log.id,
      created_at: log.created_at,
      actor: actorLabel(log),
      event_type: log.event_type,
      resource_type: log.resource_type,
      resource_id: log.resource_id,
      payload: payloadSummary(log.payload),
    }));
    const csv = [
      "id,created_at,actor,event_type,resource_type,resource_id,payload",
      ...rows.map((row) =>
        [
          row.id,
          row.created_at,
          row.actor,
          row.event_type,
          row.resource_type,
          row.resource_id,
          row.payload,
        ]
          .map(csvCell)
          .join(","),
      ),
    ].join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "pharmaide-audit-trail.csv";
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="h-full overflow-y-auto p-8">
      <div className="flex flex-col gap-6">
        <Header
          onExport={exportVisibleLogs}
          exportDisabled={filteredLogs.length === 0}
        />

        <div className="bg-white border border-slate-200 rounded-2xl overflow-hidden">
          <div className="p-4 border-b border-slate-100 flex flex-col gap-3 bg-slate-50/50 xl:flex-row xl:items-center xl:justify-between">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
              <div className="relative w-full lg:w-96">
                <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                <input
                  value={searchQuery}
                  onChange={(event) => setSearchQuery(event.target.value)}
                  placeholder="Search audits by event, resource, or actor..."
                  className="w-full pl-9 pr-4 py-2 bg-white border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-[#D9D5FB] focus:border-[#5548E8] transition-all"
                />
              </div>
              <ActorSwitch value={actorFilter} onChange={setActorFilter} />
            </div>
            <div className="flex items-center gap-2 text-xs font-bold text-slate-500 uppercase tracking-wider">
              <ShieldCheck size={14} className="text-emerald-600" />
              Metadata-only audit trail
            </div>
          </div>
          <ExactAuditFilters
            value={draftExactFilters}
            onChange={setDraftExactFilters}
            onApply={applyExactFilters}
            onClear={clearExactFilters}
          />

          {state.kind === "loading" && <LoadingState />}
          {state.kind === "error" && (
            <ErrorState requestId={state.requestId} onRetry={refresh} />
          )}
          {state.kind === "ok" && (
            <>
              {state.items.length === 0 && !hasExactFilters(appliedExactFilters) ? (
                <EmptyState />
              ) : filteredLogs.length === 0 ? (
                <NoMatchesState />
              ) : (
                <AuditTable items={filteredLogs} />
              )}

              <div className="p-4 border-t border-slate-100 bg-slate-50/50 flex items-center justify-between text-sm text-slate-500">
                <span>
                  Showing {filteredLogs.length} of {state.items.length} loaded audit entries
                </span>
                <button
                  type="button"
                  onClick={loadOlderLogs}
                  disabled={!state.hasMore || isLoadingMore}
                  className="inline-flex items-center gap-2 font-bold text-[#5548E8] hover:text-[#463AD4] transition-colors cursor-pointer disabled:cursor-not-allowed disabled:text-slate-400"
                >
                  {isLoadingMore && <Loader2 size={14} className="animate-spin" />}
                  Load older logs
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function ActorSwitch({
  value,
  onChange,
}: {
  value: ActorFilter;
  onChange: (value: ActorFilter) => void;
}) {
  return (
    <div
      className="inline-flex w-fit rounded-xl border border-slate-200 bg-white p-1"
      aria-label="Filter audits by actor"
    >
      {ACTOR_FILTERS.map((level) => (
        <button
          key={level}
          type="button"
          onClick={() => onChange(level)}
          className={`inline-flex min-w-20 items-center justify-center rounded-lg px-3 py-1.5 text-xs font-bold transition-colors cursor-pointer ${
            value === level
              ? "bg-[#5548E8] text-white"
              : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
          }`}
          aria-pressed={value === level}
        >
          {level}
          {value === level && level !== "All" && (
            <CheckCircle2 size={13} className="ml-1.5" />
          )}
        </button>
      ))}
    </div>
  );
}

function ExactAuditFilters({
  value,
  onChange,
  onApply,
  onClear,
}: {
  value: AuditExactFilters;
  onChange: (value: AuditExactFilters) => void;
  onApply: () => void;
  onClear: () => void;
}) {
  return (
    <form
      className="grid gap-3 border-b border-slate-100 bg-white p-4 lg:grid-cols-[1fr_1fr_1.4fr_auto]"
      onSubmit={(event) => {
        event.preventDefault();
        onApply();
      }}
    >
      <ExactFilterInput
        id="audit-event-type"
        label="Event type"
        value={value.event_type}
        placeholder="analysis_started"
        onChange={(event_type) => onChange({ ...value, event_type })}
      />
      <ExactFilterInput
        id="audit-resource-type"
        label="Resource type"
        value={value.resource_type}
        placeholder="treatment"
        onChange={(resource_type) => onChange({ ...value, resource_type })}
      />
      <ExactFilterInput
        id="audit-actor-id"
        label="Actor ID"
        value={value.actor_id}
        placeholder="UUID for a specific human actor"
        onChange={(actor_id) => onChange({ ...value, actor_id })}
      />
      <div className="flex items-end gap-2">
        <button
          type="submit"
          className="rounded-lg border border-[#5548E8] bg-[#5548E8] px-3 py-2 text-xs font-bold text-white transition-colors hover:bg-[#463AD4] cursor-pointer"
        >
          Apply audit filters
        </button>
        <button
          type="button"
          onClick={onClear}
          className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-bold text-slate-600 transition-colors hover:bg-slate-50 cursor-pointer"
        >
          Clear
        </button>
      </div>
    </form>
  );
}

function ExactFilterInput({
  id,
  label,
  value,
  placeholder,
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  placeholder: string;
  onChange: (value: string) => void;
}) {
  return (
    <label htmlFor={id} className="block">
      <span className="mb-1 block text-[10px] font-bold uppercase tracking-wider text-slate-500">
        {label}
      </span>
      <input
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-800 focus:border-[#5548E8] focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#D9D5FB]"
      />
    </label>
  );
}

function Header({
  onExport,
  exportDisabled,
}: {
  onExport: () => void;
  exportDisabled: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-4">
      <div>
        <h2 className="text-2xl font-bold tracking-tight text-slate-900 mb-1">
          System Audits
        </h2>
        <p className="text-sm text-slate-500">
          Immutable record of AI decisions, tool calls, delivery state, and human actions.
        </p>
      </div>
      <button
        type="button"
        onClick={onExport}
        disabled={exportDisabled}
        className="px-4 py-2 bg-[#5548E8] text-white rounded-xl font-semibold hover:bg-[#463AD4] transition-colors flex items-center gap-2 cursor-pointer disabled:cursor-not-allowed disabled:bg-slate-300"
      >
        <Download size={16} />
        Export Audit Trail
      </button>
    </div>
  );
}

function AuditTable({ items }: { items: AuditLogEntryView[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left">
        <thead>
          <tr className="bg-slate-50/50 border-b border-slate-200">
            <th className="px-6 py-4 text-[11px] font-bold tracking-wider text-slate-500 uppercase">Log ID</th>
            <th className="px-6 py-4 text-[11px] font-bold tracking-wider text-slate-500 uppercase">Timestamp</th>
            <th className="px-6 py-4 text-[11px] font-bold tracking-wider text-slate-500 uppercase">Actor</th>
            <th className="px-6 py-4 text-[11px] font-bold tracking-wider text-slate-500 uppercase">Action</th>
            <th className="px-6 py-4 text-[11px] font-bold tracking-wider text-slate-500 uppercase">Resource</th>
            <th className="px-6 py-4 text-[11px] font-bold tracking-wider text-slate-500 uppercase">Details</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {items.map((log) => (
            <tr key={log.id} className="hover:bg-slate-50/80 transition-colors">
              <td className="px-6 py-4 font-mono text-xs font-bold text-slate-900">
                {shortId(log.id)}
              </td>
              <td className="px-6 py-4 text-sm text-slate-600 whitespace-nowrap">
                {formatTimestamp(log.created_at)}
              </td>
              <td className="px-6 py-4">
                <ActorCell log={log} />
              </td>
              <td className="px-6 py-4">
                <span className="text-sm font-bold text-slate-900">
                  {titleCase(log.event_type)}
                </span>
              </td>
              <td className="px-6 py-4">
                <div className="text-sm text-slate-700 font-medium">
                  {titleCase(log.resource_type)}
                </div>
                <div className="font-mono text-xs text-slate-400">{shortId(log.resource_id)}</div>
              </td>
              <td className="px-6 py-4 text-sm text-slate-600 max-w-xl">
                {payloadSummary(log.payload)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ActorCell({ log }: { log: AuditLogEntryView }) {
  const label = actorLabel(log);
  const iconClass =
    label === "Agent"
      ? "bg-[#F0EFFF] text-[#463AD4]"
      : label === "Human"
        ? "bg-yellow-50 text-yellow-700"
        : "bg-slate-100 text-slate-600";
  return (
    <div className="flex items-center gap-2">
      <div className={`w-7 h-7 rounded-md flex items-center justify-center ${iconClass}`}>
        {label === "Agent" ? (
          <Bot size={14} />
        ) : label === "Human" ? (
          <User size={14} />
        ) : (
          <Zap size={14} />
        )}
      </div>
      <span className="text-sm font-medium text-slate-700">{label}</span>
    </div>
  );
}

function LoadingState() {
  return (
    <div className="p-10 flex items-center justify-center gap-3 text-slate-600">
      <Loader2 size={18} className="animate-spin" />
      Loading audit trail
    </div>
  );
}

function EmptyState() {
  return (
    <div className="p-10 text-center">
      <ShieldCheck className="mx-auto mb-3 text-slate-400" size={28} />
      <h3 className="text-base font-bold text-slate-900">No audit events recorded yet.</h3>
      <p className="mt-1 text-sm text-slate-500">
        Clinical actions and AI workflow decisions will appear here when they occur.
      </p>
    </div>
  );
}

function NoMatchesState() {
  return (
    <div className="p-10 text-center">
      <Search className="mx-auto mb-3 text-slate-400" size={28} />
      <h3 className="text-base font-bold text-slate-900">No audit events match this filter.</h3>
      <p className="mt-1 text-sm text-slate-500">Adjust the search or actor filter.</p>
    </div>
  );
}

function ErrorState({
  requestId,
  onRetry,
}: {
  requestId: string | null;
  onRetry: () => void;
}) {
  return (
    <div className="m-4 border border-amber-300 bg-amber-50 rounded-xl p-6 flex items-center justify-between gap-4">
      <div className="flex items-start gap-3">
        <AlertCircle className="text-amber-700 mt-0.5" size={22} />
        <div>
          <h3 className="font-bold text-slate-900">Audit trail is temporarily unavailable.</h3>
          <p className="text-sm text-slate-600">
            Please retry. Reference ID: {requestId ?? "unknown"}
          </p>
        </div>
      </div>
      <button
        type="button"
        onClick={onRetry}
        className="inline-flex items-center gap-2 px-4 py-2 bg-white border border-slate-200 rounded-xl font-bold text-slate-700 hover:bg-slate-50 cursor-pointer"
      >
        <RefreshCw size={16} />
        Retry
      </button>
    </div>
  );
}

function actorLabel(log: AuditLogEntryView): ActorFilter {
  if (log.actor_id) return "Human";
  if (
    log.event_type.includes("analysis") ||
    log.event_type.includes("safety") ||
    log.event_type.includes("retrieval") ||
    log.event_type.includes("conversation_turn")
  ) {
    return "Agent";
  }
  return "System";
}

function auditRequestId(err: unknown): string | null {
  return err instanceof ApiError ? err.requestId : null;
}

function requestFilters(filters: AuditExactFilters): Partial<AuditExactFilters> {
  const normalised = normaliseExactFilters(filters);
  return Object.fromEntries(
    Object.entries(normalised).filter(([, value]) => value.length > 0),
  ) as Partial<AuditExactFilters>;
}

function normaliseExactFilters(filters: AuditExactFilters): AuditExactFilters {
  return {
    event_type: filters.event_type.trim(),
    resource_type: filters.resource_type.trim(),
    actor_id: filters.actor_id.trim(),
  };
}

function hasExactFilters(filters: AuditExactFilters): boolean {
  return Object.values(filters).some((value) => value.trim().length > 0);
}

function payloadSummary(payload: Record<string, unknown>): string {
  const entries = Object.entries(payload);
  if (entries.length === 0) return "No additional metadata";
  return entries.map(([key, value]) => `${key}: ${String(value)}`).join(" · ");
}

function titleCase(value: string): string {
  return value
    .split("_")
    .filter(Boolean)
    .map((part) => part[0].toUpperCase() + part.slice(1))
    .join(" ");
}

function shortId(value: string): string {
  return value.slice(0, 8);
}

function formatTimestamp(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function csvCell(value: string): string {
  return `"${value.replaceAll('"', '""')}"`;
}
