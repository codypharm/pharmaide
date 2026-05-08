import { Clock, Filter, Zap, TrendingUp, Users, MessageSquare, CheckCircle2, MoreVertical, Bell } from "lucide-react";
import { useOutletContext } from "react-router-dom";

type OutletContext = {
  isPrivacyMode: boolean;
};

const MOCK_ESCALATIONS = [
  {
    id: "P-4492",
    patientName: "Jameson, M.",
    medication: "Lisinopril 20mg",
    reason: "Persistent dry cough — patient self-discontinued ACE inhibitor",
    severity: "critical",
    time: "10m ago",
  },
  {
    id: "P-8821",
    patientName: "Chen, L.",
    medication: "Metformin 500mg",
    reason: "Missed 3 consecutive doses, GI distress reported",
    severity: "warning",
    time: "1h ago",
  },
  {
    id: "P-3345",
    patientName: "Garcia, R.",
    medication: "Apixaban 5mg",
    reason: "Reporting bruising — potential DDI with new NSAID prescription",
    severity: "warning",
    time: "2h ago",
  },
];

const MOCK_INTERVENTIONS = [
  { id: "P-1102", patientName: "Smith, A.", status: "Pending Rx Auth", priority: "High", assignedTo: "Unassigned" },
  { id: "P-3345", patientName: "Garcia, R.", status: "Awaiting Lab Results", priority: "Medium", assignedTo: "Dr. Thorne" },
  { id: "P-7734", patientName: "Miller, T.", status: "Follow-up Scheduled", priority: "Low", assignedTo: "Dr. Thorne" },
];

const MOCK_AGENT_ACTIVITY = [
  { icon: MessageSquare, text: "WhatsApp message sent to P-4492 re: cough side effect", time: "2m ago", color: "text-blue-500" },
  { icon: CheckCircle2, text: "Adherence check completed for 48 patients on Cardio-01", time: "8m ago", color: "text-emerald-500" },
  { icon: Bell, text: "DDI flag raised — Rivaroxaban + Paxlovid conflict (P-8992)", time: "15m ago", color: "text-slate-500" },
  { icon: Zap, text: "AI triage summary generated for morning handoff report", time: "1h ago", color: "text-yellow-500" },
];

export default function TriageQueuePage() {
  const { isPrivacyMode } = useOutletContext<OutletContext>();

  return (
    <div className="flex flex-col gap-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-slate-900 mb-1">Triage Queue</h2>
          <p className="text-sm text-slate-500">Real-time pharmacist interventions and AI-flagged escalations.</p>
        </div>
        <div className="flex gap-3">
          <button className="px-4 py-2 bg-white border border-slate-200 text-slate-700 rounded-xl font-semibold hover:bg-slate-50 transition-colors shadow-sm flex items-center gap-2">
            <Filter size={16} />
            Filter Queue
          </button>
        </div>
      </div>

      {/* System Health Metrics */}
      <div className="grid grid-cols-4 gap-4">
        <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm">
          <div className="flex items-center justify-between mb-3">
            <p className="text-xs font-bold tracking-wider text-slate-400 uppercase">Total Queue</p>
            <div className="w-8 h-8 bg-blue-50 text-blue-600 rounded-lg flex items-center justify-center">
              <Users size={16} />
            </div>
          </div>
          <p className="text-3xl font-bold text-slate-900">24</p>
          <p className="text-xs text-slate-500 mt-1">+3 since last shift</p>
        </div>
        <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm">
          <div className="flex items-center justify-between mb-3">
            <p className="text-xs font-bold tracking-wider text-slate-400 uppercase">Critical</p>
          </div>
          <p className="text-3xl font-bold text-red-600">3</p>
          <p className="text-xs text-slate-500 mt-1">Require immediate action</p>
        </div>
        <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm">
          <div className="flex items-center justify-between mb-3">
            <p className="text-xs font-bold tracking-wider text-slate-400 uppercase">Avg Wait</p>
            <div className="w-8 h-8 bg-yellow-50 text-yellow-500 rounded-lg flex items-center justify-center">
              <Clock size={16} />
            </div>
          </div>
          <p className="text-3xl font-bold text-slate-900">12<span className="text-sm text-slate-400 font-medium ml-1">min</span></p>
          <p className="text-xs text-slate-500 mt-1">Target: &lt;15 min</p>
        </div>
        <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm">
          <div className="flex items-center justify-between mb-3">
            <p className="text-xs font-bold tracking-wider text-slate-400 uppercase">Resolved Today</p>
            <div className="w-8 h-8 bg-emerald-50 text-emerald-500 rounded-lg flex items-center justify-center">
              <TrendingUp size={16} />
            </div>
          </div>
          <p className="text-3xl font-bold text-slate-900">17</p>
          <p className="text-xs text-slate-500 mt-1">↑ 24% vs yesterday</p>
        </div>
      </div>

      {/* Critical DDI Alert Banner */}
      <div className="bg-white border border-slate-200 rounded-2xl p-4 flex items-center gap-4 shadow-sm">
        <div className="flex-1">
          <p className="font-bold text-sm text-red-600">Critical DDI Alert — Immediate Review Required</p>
          <p className="text-sm text-slate-600">Patient P-8992 initiated on Paxlovid while active on Rivaroxaban. Contraindicated combination — significant bleeding risk.</p>
        </div>
        <button className="px-4 py-2 bg-red-600 text-white rounded-xl text-sm font-bold shadow-sm shadow-red-200 hover:bg-red-700 transition-colors whitespace-nowrap">
          Review Now
        </button>
      </div>

      {/* Main 2-column layout */}
      <div className="grid lg:grid-cols-3 gap-6">
        {/* Left — Escalations (2/3 width) */}
        <div className="lg:col-span-2 flex flex-col gap-6">
          {/* Active Escalations */}
          <div className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden">
            <div className="p-5 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
              <div>
                <h3 className="font-bold text-lg text-slate-900">Active Escalations</h3>
                <p className="text-sm text-slate-500">AI-flagged conversations requiring human review.</p>
              </div>
              <span className="bg-blue-100 text-blue-700 px-3 py-1 rounded-full text-xs font-bold tracking-wider">
                {MOCK_ESCALATIONS.length} PENDING
              </span>
            </div>
            <div className="p-5 flex flex-col gap-4">
              {MOCK_ESCALATIONS.map((escalation) => (
                <div
                  key={escalation.id}
                  className="p-4 rounded-xl border border-slate-200 bg-white flex items-start justify-between gap-4 transition-colors hover:border-slate-300 shadow-sm"
                >
                  <div className="flex gap-4">
                    <div className="flex-1">
                      <div className="flex items-center gap-3 mb-1">
                        <span className="font-mono text-sm font-bold text-slate-900">ID: {escalation.id}</span>
                        <span
                          className={`text-sm font-medium transition-all duration-300 ${
                            isPrivacyMode
                              ? "blur-sm hover:blur-none cursor-pointer select-none"
                              : "text-slate-600"
                          }`}
                        >
                          {escalation.patientName}
                        </span>
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-bold tracking-wider uppercase ${
                            escalation.severity === "critical"
                              ? "bg-red-200 text-red-800"
                              : "bg-amber-200 text-amber-800"
                          }`}
                        >
                          {escalation.severity}
                        </span>
                      </div>
                      <p className="text-sm font-semibold text-slate-900 mb-1">{escalation.medication}</p>
                      <p className="text-sm text-slate-600">{escalation.reason}</p>
                    </div>
                  </div>
                  <div className="flex flex-col items-end gap-3 shrink-0">
                    <span className="flex items-center gap-1.5 text-xs font-bold tracking-wider text-slate-400 uppercase">
                      <Clock size={12} /> {escalation.time}
                    </span>
                    <button className="px-4 py-1.5 bg-white border border-slate-200 rounded-lg text-sm font-semibold hover:bg-slate-50 shadow-sm transition-colors">
                      Resolve
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Pending Interventions Table */}
          <div className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden">
            <div className="p-5 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
              <div>
                <h3 className="font-bold text-lg text-slate-900">Pending Interventions</h3>
                <p className="text-sm text-slate-500">Open pharmacist tasks awaiting action.</p>
              </div>
            </div>
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-slate-100">
                  <th className="px-5 py-3 text-[11px] font-bold tracking-wider text-slate-400 uppercase">Patient</th>
                  <th className="px-5 py-3 text-[11px] font-bold tracking-wider text-slate-400 uppercase">Status</th>
                  <th className="px-5 py-3 text-[11px] font-bold tracking-wider text-slate-400 uppercase">Priority</th>
                  <th className="px-5 py-3 text-[11px] font-bold tracking-wider text-slate-400 uppercase">Assigned To</th>
                  <th className="px-5 py-3"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {MOCK_INTERVENTIONS.map((iv) => (
                  <tr key={iv.id} className="hover:bg-slate-50 transition-colors">
                    <td className="px-5 py-4">
                      <div className="flex flex-col gap-0.5">
                        <span className="font-mono text-sm font-bold text-slate-900">{iv.id}</span>
                        <span
                          className={`text-sm transition-all duration-300 ${
                            isPrivacyMode
                              ? "blur-sm hover:blur-none cursor-pointer text-slate-600"
                              : "text-slate-600"
                          }`}
                        >
                          {iv.patientName}
                        </span>
                      </div>
                    </td>
                    <td className="px-5 py-4 text-sm text-slate-700 font-medium">{iv.status}</td>
                    <td className="px-5 py-4">
                      <span
                        className={`px-2.5 py-1 rounded-md text-[10px] font-bold tracking-wider uppercase ${
                          iv.priority === "High"
                            ? "bg-red-100 text-red-700"
                            : iv.priority === "Medium"
                            ? "bg-amber-100 text-amber-700"
                            : "bg-slate-100 text-slate-600"
                        }`}
                      >
                        {iv.priority}
                      </span>
                    </td>
                    <td className="px-5 py-4">
                      <div className="flex items-center gap-2 text-sm text-slate-600">
                        <div className={`w-2 h-2 rounded-full ${iv.assignedTo === "Unassigned" ? "bg-slate-300" : "bg-emerald-400"}`} />
                        {iv.assignedTo}
                      </div>
                    </td>
                    <td className="px-5 py-4 text-right">
                      <button className="text-slate-400 hover:text-slate-700">
                        <MoreVertical size={16} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Right — Agent Activity Feed (1/3 width) */}
        <div className="flex flex-col gap-4">
          <div className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden">
            <div className="p-5 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
              <h3 className="font-bold text-slate-900">Agent Activity</h3>
              <div className="flex items-center gap-1.5">
                <div className="w-2 h-2 bg-emerald-400 rounded-full animate-pulse" />
                <span className="text-xs font-bold text-emerald-600 uppercase tracking-wider">Live</span>
              </div>
            </div>
            <div className="divide-y divide-slate-100">
              {MOCK_AGENT_ACTIVITY.map((item, i) => {
                const Icon = item.icon;
                return (
                  <div key={i} className="p-4 hover:bg-slate-50 transition-colors flex gap-3">
                    <div className="mt-0.5">
                      <Icon size={16} className={item.color} />
                    </div>
                    <div>
                      <p className="text-sm text-slate-700 leading-snug">{item.text}</p>
                      <p className="text-xs text-slate-400 mt-1 font-medium">{item.time}</p>
                    </div>
                  </div>
                );
              })}
            </div>
            <div className="p-4 border-t border-slate-100 bg-slate-50/50">
              <button className="text-xs font-bold text-blue-600 hover:text-blue-700 transition-colors">
                View full audit log →
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
