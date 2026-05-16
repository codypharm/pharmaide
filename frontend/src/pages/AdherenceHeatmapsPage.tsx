import {
  AlertCircle,
  Calendar,
  Clock,
  Loader2,
  Search,
} from "lucide-react";
import type { CSSProperties } from "react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useOutletContext } from "react-router-dom";

import { ApiError } from "../api/client";
import {
  listAdherenceEvents,
  listTreatments,
  type AdherenceEventStatus,
  type AdherenceEventView,
  type TreatmentListItem,
} from "../api/treatments";

type OutletContext = {
  isPrivacyMode: boolean;
};

type TreatmentAdherenceRow = {
  treatment: TreatmentListItem;
  events: AdherenceEventView[];
};

type FetchState =
  | { kind: "loading" }
  | { kind: "ok"; rows: TreatmentAdherenceRow[] }
  | { kind: "error"; requestId: string | null };

const PAGE_SIZE = 50;
const ADHERENCE_STATUSES: AdherenceEventStatus[] = ["taken", "missed", "held", "skipped"];
const DATE_RANGE_OPTIONS = [
  { label: "Last 7 days", value: 7 },
  { label: "Last 30 days", value: 30 },
  { label: "Last 90 days", value: 90 },
] as const;

export default function AdherenceHeatmapsPage() {
  const { isPrivacyMode } = useOutletContext<OutletContext>();
  const [searchTerm, setSearchTerm] = useState("");
  const [dateRangeDays, setDateRangeDays] = useState(30);
  const [state, setState] = useState<FetchState>({ kind: "loading" });

  const refresh = useCallback(async () => {
    setState({ kind: "loading" });
    try {
      const treatmentList = await listTreatments({ limit: PAGE_SIZE, offset: 0 });
      const rows = await Promise.all(
        treatmentList.items.map(async (treatment) => ({
          treatment,
          events: (await listAdherenceEvents(treatment.treatment.id)).items,
        })),
      );
      setState({ kind: "ok", rows });
    } catch (err) {
      setState({ kind: "error", requestId: requestIdFromError(err) });
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const days = useMemo(() => lastNDays(dateRangeDays), [dateRangeDays]);

  const rowsInDateRange = useMemo(() => {
    if (state.kind !== "ok") return [];
    return state.rows.map((row) => ({
      ...row,
      events: eventsInDateRange(row.events, days),
    }));
  }, [days, state]);

  const visibleRows = useMemo(() => {
    const query = searchTerm.trim().toLowerCase();
    return rowsInDateRange
      .filter((row) => {
        if (!query) return true;
        return [
          row.treatment.patient.name,
          row.treatment.patient.mrn,
          row.treatment.treatment.id,
          row.treatment.first_medication_name,
        ]
          .join(" ")
          .toLowerCase()
          .includes(query);
      })
      .sort((a, b) => riskScore(b.events) - riskScore(a.events));
  }, [rowsInDateRange, searchTerm]);

  const totals = adherenceTotals(rowsInDateRange.flatMap((row) => row.events));

  return (
    <div className="h-full overflow-y-auto p-8 bg-[#F5F5F6]">
      <div className="flex flex-col gap-6 w-full">
        <header className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-[#F0EFFF] text-[#5548E8] rounded-xl flex items-center justify-center">
              <Calendar size={20} />
            </div>
            <div>
              <h2 className="text-2xl font-bold tracking-tight text-slate-900 mb-1">
                Adherence
              </h2>
              <p className="text-sm text-slate-500 font-medium">
                Real adherence events recorded from patient check-ins and reminder state.
              </p>
            </div>
          </div>
          <label className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-[11px] font-bold uppercase tracking-wider text-slate-500">
            <Calendar size={14} />
            <select
              aria-label="Adherence date range"
              value={dateRangeDays}
              onChange={(event) => setDateRangeDays(Number(event.target.value))}
              className="bg-transparent text-[11px] font-bold uppercase tracking-wider text-slate-600 outline-none cursor-pointer"
            >
              {DATE_RANGE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
        </header>

        <SummaryBand totals={totals} />

        <section className="bg-white border border-slate-200 rounded-2xl overflow-hidden">
          <div className="p-4 border-b border-slate-100 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between bg-slate-50/50">
            <div className="relative w-full lg:w-96">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                type="text"
                placeholder="Search patient, MRN, medication, or treatment..."
                value={searchTerm}
                onChange={(event) => setSearchTerm(event.target.value)}
                className="w-full pl-9 pr-4 py-2 bg-white border border-slate-200 rounded-lg text-xs focus:outline-none focus:ring-2 focus:ring-[#D9D5FB] focus:border-[#5548E8] transition-all"
              />
            </div>
            <Legend />
          </div>

          {state.kind === "loading" && <LoadingState />}
          {state.kind === "error" && <ErrorState requestId={state.requestId} onRetry={refresh} />}
          {state.kind === "ok" && state.rows.length === 0 && <EmptyState />}
          {state.kind === "ok" && state.rows.length > 0 && visibleRows.length === 0 && (
            <NoMatchesState />
          )}
          {state.kind === "ok" && visibleRows.length > 0 && (
            <AdherenceTable rows={visibleRows} days={days} isPrivacyMode={isPrivacyMode} />
          )}
        </section>
      </div>
    </div>
  );
}

function SummaryBand({ totals }: { totals: Record<AdherenceEventStatus, number> }) {
  return (
    <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
      <SummaryCard label="Taken" value={totals.taken} tone="primary" />
      <SummaryCard label="Missed" value={totals.missed} tone="red" />
      <SummaryCard label="Held" value={totals.held} tone="amber" />
      <SummaryCard label="Skipped" value={totals.skipped} tone="slate" />
    </div>
  );
}

function SummaryCard({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: "primary" | "red" | "amber" | "slate";
}) {
  const color = {
    primary: "text-[#5548E8]",
    red: "text-red-700",
    amber: "text-amber-700",
    slate: "text-slate-700",
  }[tone];

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5">
      <p className="text-[11px] font-bold uppercase tracking-wider text-slate-500">{label}</p>
      <p className={`mt-3 text-3xl font-black tabular-nums ${color}`}>{value}</p>
    </div>
  );
}

function Legend() {
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-lg border border-slate-100 bg-white px-3 py-2">
      {ADHERENCE_STATUSES.map((status) => (
        <div key={status} className="flex items-center gap-2">
          <span className={`h-2.5 w-2.5 rounded-[2px] ${statusColor(status)}`} />
          <span className="text-[9px] font-bold tracking-wider text-slate-500 uppercase">
            {statusLabel(status)}
          </span>
        </div>
      ))}
      <div className="flex items-center gap-2">
        <span className="h-2.5 w-2.5 rounded-[2px] bg-slate-100" />
        <span className="text-[9px] font-bold tracking-wider text-slate-500 uppercase">
          No data
        </span>
      </div>
    </div>
  );
}

function AdherenceTable({
  rows,
  days,
  isPrivacyMode,
}: {
  rows: TreatmentAdherenceRow[];
  days: DayWindow[];
  isPrivacyMode: boolean;
}) {
  return (
    <div className="overflow-x-auto p-6">
      <div className="min-w-[980px]">
        <div
          className="grid items-center gap-1 pb-3 text-[10px] font-bold uppercase tracking-wider text-slate-400"
          style={adherenceGridTemplate(days.length)}
        >
          <span>Patient</span>
          {days.map((day) => (
            <span key={day.key} className="text-center">
              {day.label}
            </span>
          ))}
          <span className="pl-4">Recent adherence events</span>
        </div>

        <div className="divide-y divide-slate-100">
          {rows.map((row) => (
            <TreatmentAdherenceRowView
              key={row.treatment.treatment.id}
              row={row}
              days={days}
              isPrivacyMode={isPrivacyMode}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

function TreatmentAdherenceRowView({
  row,
  days,
  isPrivacyMode,
}: {
  row: TreatmentAdherenceRow;
  days: DayWindow[];
  isPrivacyMode: boolean;
}) {
  const eventByDay = latestEventByDay(row.events);
  const totals = adherenceTotals(row.events);
  const recentEvents = [...row.events]
    .sort((a, b) => eventTimeMs(b) - eventTimeMs(a))
    .slice(0, 2);
  const patientClass = isPrivacyMode ? "blur-sm select-none" : "";

  return (
    <article
      className="grid items-center gap-1 py-3"
      style={adherenceGridTemplate(days.length)}
    >
      <div className="pr-4">
        <p className={`truncate text-sm font-bold text-slate-900 ${patientClass}`}>
          {row.treatment.patient.name}
        </p>
        <p className={`mt-0.5 truncate text-[11px] font-semibold text-slate-500 ${patientClass}`}>
          {row.treatment.patient.mrn}
        </p>
        <p className="mt-1 truncate text-[11px] font-bold text-slate-700">
          {row.treatment.first_medication_name ?? "Medication not listed"}
        </p>
        <div className="mt-2 flex gap-2 text-[10px] font-bold tabular-nums text-slate-500">
          <span>Taken {totals.taken}</span>
          <span>Missed {totals.missed}</span>
        </div>
      </div>

      {days.map((day) => {
        const event = eventByDay.get(day.key);
        return (
          <div
            key={day.key}
            title={`${day.key}: ${event ? statusLabel(event.status) : "No data"}`}
            className={`mx-auto h-7 w-4 rounded-[3px] ${
              event ? statusColor(event.status) : "bg-slate-100"
            }`}
          />
        );
      })}

      <div className="pl-4">
        {recentEvents.length === 0 ? (
          <p className="text-xs font-medium text-slate-400">No adherence events recorded.</p>
        ) : (
          <div className="space-y-2">
            {recentEvents.map((event) => (
              <RecentEvent key={event.id} event={event} />
            ))}
          </div>
        )}
      </div>
    </article>
  );
}

function RecentEvent({ event }: { event: AdherenceEventView }) {
  return (
    <div className="rounded-lg border border-slate-100 bg-slate-50 px-3 py-2">
      <div className="flex items-center justify-between gap-3">
        <span className={`rounded-full px-2 py-0.5 text-[9px] font-black uppercase tracking-wider text-white ${statusColor(event.status)}`}>
          {statusLabel(event.status)}
        </span>
        <span className="text-[10px] font-semibold text-slate-400">
          {formatDate(event.occurred_at ?? event.scheduled_for ?? event.created_at)}
        </span>
      </div>
      {event.note && <p className="mt-1 text-xs leading-5 text-slate-600">{event.note}</p>}
    </div>
  );
}

function LoadingState() {
  return (
    <div className="p-10 flex items-center justify-center gap-2 text-sm text-slate-500">
      <Loader2 size={16} className="animate-spin" />
      Loading adherence state...
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
    <div className="m-4 rounded-xl border border-amber-200 bg-amber-50 p-5 flex items-center justify-between gap-4">
      <div className="flex items-start gap-3">
        <AlertCircle size={18} className="mt-0.5 text-amber-700" />
        <div>
          <p className="font-bold text-slate-900">Could not load adherence data.</p>
          <p className="mt-1 text-sm text-slate-600">
            Please retry. Reference ID: {requestId ?? "unknown"}
          </p>
        </div>
      </div>
      <button
        type="button"
        onClick={onRetry}
        className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-bold text-slate-700 hover:bg-slate-50 cursor-pointer"
      >
        Retry
      </button>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="p-12 text-center">
      <Clock size={30} className="mx-auto mb-3 text-slate-300" />
      <p className="font-bold text-slate-900">No adherence data yet.</p>
      <p className="mt-1 text-sm text-slate-500">
        Create a treatment before adherence tracking can start.
      </p>
    </div>
  );
}

function NoMatchesState() {
  return (
    <div className="p-12 text-center">
      <Search size={30} className="mx-auto mb-3 text-slate-300" />
      <p className="font-bold text-slate-900">No matching adherence rows.</p>
      <p className="mt-1 text-sm text-slate-500">Adjust the search term.</p>
    </div>
  );
}

function latestEventByDay(events: AdherenceEventView[]): Map<string, AdherenceEventView> {
  const latest = new Map<string, AdherenceEventView>();
  for (const event of events) {
    const key = dayKey(event.scheduled_for ?? event.occurred_at ?? event.created_at);
    const existing = latest.get(key);
    if (!existing || eventTimeMs(event) > eventTimeMs(existing)) {
      latest.set(key, event);
    }
  }
  return latest;
}

function eventsInDateRange(
  events: AdherenceEventView[],
  days: DayWindow[],
): AdherenceEventView[] {
  const allowedDays = new Set(days.map((day) => day.key));
  return events.filter((event) =>
    allowedDays.has(dayKey(event.scheduled_for ?? event.occurred_at ?? event.created_at)),
  );
}

function adherenceTotals(events: AdherenceEventView[]): Record<AdherenceEventStatus, number> {
  const totals = emptyTotals();
  for (const event of events) {
    totals[event.status] += 1;
  }
  return totals;
}

function emptyTotals(): Record<AdherenceEventStatus, number> {
  return { taken: 0, missed: 0, held: 0, skipped: 0 };
}

type DayWindow = {
  key: string;
  label: string;
};

function lastNDays(count: number): DayWindow[] {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Array.from({ length: count }, (_, index) => {
    const date = new Date(today);
    date.setDate(today.getDate() - (count - index - 1));
    return {
      key: localDayKey(date),
      label: String(date.getDate()),
    };
  });
}

function adherenceGridTemplate(dayCount: number): CSSProperties {
  return {
    gridTemplateColumns: `220px repeat(${dayCount}, minmax(16px, 1fr)) 260px`,
  };
}

function dayKey(value: string): string {
  return localDayKey(new Date(value));
}

function localDayKey(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function eventTimeMs(event: AdherenceEventView): number {
  return new Date(event.occurred_at ?? event.scheduled_for ?? event.created_at).getTime();
}

function riskScore(events: AdherenceEventView[]): number {
  return events.filter((event) => event.status === "missed" || event.status === "held").length;
}

function statusLabel(status: string): string {
  return status.charAt(0).toUpperCase() + status.slice(1);
}

function statusColor(status: string): string {
  switch (status) {
    case "taken":
      return "bg-[#5548E8]";
    case "missed":
      return "bg-red-600";
    case "held":
      return "bg-amber-500";
    case "skipped":
      return "bg-slate-500";
    default:
      return "bg-slate-100";
  }
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

function requestIdFromError(err: unknown): string | null {
  return err instanceof ApiError ? err.requestId : null;
}
