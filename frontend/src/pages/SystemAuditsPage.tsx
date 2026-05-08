import { useState } from "react";
import { Search, Filter, Download, ShieldCheck, User, Bot, Zap, CheckCircle2 } from "lucide-react";

const AUDIT_LOGS = [
  { id: "LOG-9921", time: "Oct 24, 10:42 AM", actor: "AI Agent", action: "Clinical Flag Raised", details: "DDI flag: Rivaroxaban + Paxlovid (P-8992)", type: "ai" },
  { id: "LOG-9920", time: "Oct 24, 10:38 AM", actor: "Dr. Thorne", action: "Intervention Resolved", details: "P-4492: Switched to Amlodipine 5mg", type: "user" },
  { id: "LOG-9919", time: "Oct 24, 10:15 AM", actor: "System", action: "Protocol Initiated", details: "Cardio-01 started for P-1102", type: "system" },
  { id: "LOG-9918", time: "Oct 24, 09:54 AM", actor: "AI Agent", action: "Message Sent", details: "Daily adherence check-in (WhatsApp)", type: "ai" },
  { id: "LOG-9917", time: "Oct 24, 09:30 AM", actor: "Thomas F.", action: "Login", details: "Terminal session started", type: "user" },
];

export default function SystemAuditsPage() {
  const [searchQuery, setSearchQuery] = useState("");
  const [actorFilter, setActorFilter] = useState("All");
  const [showFilterMenu, setShowFilterMenu] = useState(false);

  const filteredLogs = AUDIT_LOGS.filter(log => {
    const matchesSearch = log.id.toLowerCase().includes(searchQuery.toLowerCase()) || 
                          log.actor.toLowerCase().includes(searchQuery.toLowerCase()) ||
                          log.action.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesActor = actorFilter === "All" || 
                         (actorFilter === "AI Agent" && log.type === "ai") ||
                         (actorFilter === "Human" && log.type === "user") ||
                         (actorFilter === "System" && log.type === "system");
    return matchesSearch && matchesActor;
  });

  return (
    <div className="h-full overflow-y-auto p-8">
      <div className="flex flex-col gap-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-bold tracking-tight text-slate-900 mb-1">System Audits</h2>
            <p className="text-sm text-slate-500">Immutable record of all AI decisions, tool calls, and human actions.</p>
          </div>
          <div className="flex gap-3 relative">
            <button 
              onClick={() => setShowFilterMenu(!showFilterMenu)}
              className={`px-4 py-2 border rounded-xl font-semibold transition-all shadow-sm flex items-center gap-2 cursor-pointer ${actorFilter !== 'All' ? 'bg-blue-600 text-white border-blue-600' : 'bg-white border-slate-200 text-slate-700 hover:bg-slate-50'}`}
            >
              <Filter size={16} />
              {actorFilter === 'All' ? 'Filter Logs' : `Actor: ${actorFilter}`}
            </button>
            {showFilterMenu && (
              <div className="absolute top-12 right-0 w-48 bg-white border border-slate-200 rounded-xl shadow-xl z-50 py-2 overflow-hidden animate-in fade-in zoom-in duration-200">
                <p className="px-4 py-2 text-[10px] font-black text-slate-400 uppercase tracking-widest border-b border-slate-50 mb-1">Filter by Actor</p>
                {["All", "AI Agent", "Human", "System"].map((level) => (
                  <button
                    key={level}
                    onClick={() => { setActorFilter(level); setShowFilterMenu(false); }}
                    className={`w-full px-4 py-2 text-sm text-left hover:bg-slate-50 transition-colors flex items-center justify-between font-medium ${actorFilter === level ? 'text-blue-600 bg-blue-50/50' : 'text-slate-600'}`}
                  >
                    {level}
                    {actorFilter === level && <CheckCircle2 size={14} />}
                  </button>
                ))}
              </div>
            )}
            <button className="px-4 py-2 bg-blue-600 text-white rounded-xl font-semibold hover:bg-blue-700 transition-colors shadow-sm shadow-blue-200 flex items-center gap-2 cursor-pointer">
              <Download size={16} />
              Export Audit Trail
            </button>
          </div>
        </div>

        <div className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden">
          <div className="p-4 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
            <div className="relative w-80">
              <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input 
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search by ID, actor, or action..." 
                className="w-full pl-9 pr-4 py-1.5 bg-white border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-100 focus:border-blue-500 transition-all"
              />
            </div>
            <div className="flex items-center gap-2 text-xs font-bold text-slate-400 uppercase tracking-wider">
              <ShieldCheck size={14} className="text-emerald-500" />
              HIPAA Compliant Logging
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="bg-slate-50/50 border-b border-slate-200">
                  <th className="px-6 py-4 text-[11px] font-bold tracking-wider text-slate-500 uppercase">Log ID</th>
                  <th className="px-6 py-4 text-[11px] font-bold tracking-wider text-slate-500 uppercase">Timestamp</th>
                  <th className="px-6 py-4 text-[11px] font-bold tracking-wider text-slate-500 uppercase">Actor</th>
                  <th className="px-6 py-4 text-[11px] font-bold tracking-wider text-slate-500 uppercase">Action</th>
                  <th className="px-6 py-4 text-[11px] font-bold tracking-wider text-slate-500 uppercase">Details</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredLogs.map((log) => (
                  <tr key={log.id} className="hover:bg-slate-50/80 transition-colors group cursor-pointer">
                    <td className="px-6 py-4 font-mono text-xs font-bold text-slate-900 group-hover:text-blue-600 transition-colors">{log.id}</td>
                    <td className="px-6 py-4 text-sm text-slate-600">{log.time}</td>
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-2">
                        <div className={`w-6 h-6 rounded-md flex items-center justify-center ${
                          log.type === 'ai' ? 'bg-blue-50 text-blue-600' :
                          log.type === 'user' ? 'bg-yellow-50 text-yellow-700' :
                          'bg-slate-100 text-slate-500'
                        }`}>
                          {log.type === 'ai' ? <Bot size={14} /> :
                           log.type === 'user' ? <User size={14} /> :
                           <Zap size={14} />}
                        </div>
                        <span className="text-sm font-medium text-slate-700">{log.actor}</span>
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <span className="text-sm font-bold text-slate-900">{log.action}</span>
                    </td>
                    <td className="px-6 py-4 text-sm text-slate-600">{log.details}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          
          <div className="p-4 border-t border-slate-100 bg-slate-50/50 flex items-center justify-between text-sm text-slate-500">
            <span>Showing latest {filteredLogs.length} audit entries</span>
            <button className="font-bold text-blue-600 hover:text-blue-700 transition-colors cursor-pointer">Load older logs</button>
          </div>
        </div>
      </div>
    </div>
  );
}
