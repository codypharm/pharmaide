import { 
  Search, 
  Upload, 
  Database, 
  ShieldCheck, 
  Bot, 
  FileText, 
  ChevronRight, 
  MoreHorizontal, 
  Plus, 
  RefreshCw, 
  AlertCircle,
  FileCode,
  FileSpreadsheet,
  Activity
} from "lucide-react";
import { useState } from "react";
import { useOutletContext } from "react-router-dom";

type OutletContext = {
  isPrivacyMode: boolean;
};

const DATA_SOURCES = [
  { 
    name: "Clinical Guidelines v4.2", 
    file: "clinical_guidelines_2023_v4.2.pdf", 
    type: "PDF", 
    status: "Indexed", 
    agents: ["TA", "RA"], 
    date: "Oct 24, 2023", 
    time: "14:32 PST" 
  },
  { 
    name: "Drug Interaction Database", 
    file: "interactions_q4_export.csv", 
    type: "CSV", 
    status: "Indexed", 
    agents: ["RV"], 
    date: "Oct 22, 2023", 
    time: "09:15 PST" 
  },
  { 
    name: "Fall Risk Protocol", 
    file: "fall_risk_assessment_draft.pdf", 
    type: "PDF", 
    status: "Parsing Error", 
    agents: [], 
    date: "Just now", 
    time: "",
    error: true
  },
];

export default function KnowledgeBasePage() {
  const { isPrivacyMode } = useOutletContext<OutletContext>();
  const [searchQuery, setSearchQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState("All Source Types");

  const filteredSources = DATA_SOURCES.filter(source => {
    const matchesSearch = source.name.toLowerCase().includes(searchQuery.toLowerCase()) || 
                          source.file.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesType = typeFilter === "All Source Types" || 
                        (typeFilter === "PDF Documents" && source.type === "PDF") ||
                        (typeFilter === "CSV Databases" && source.type === "CSV");
    return matchesSearch && matchesType;
  });

  return (
    <div className="h-full overflow-y-auto p-8">
      <div className="flex flex-col gap-6">
        <div className="flex items-center justify-between">
          <div className="flex flex-col gap-1">
            <h2 className="text-2xl font-bold tracking-tight text-slate-900">Knowledge Base & Agent Intelligence</h2>
            <p className="text-sm text-slate-500">Manage and upload clinical guidelines and drug databases to ground AI agent responses.</p>
          </div>
          <button className="px-4 py-2 bg-slate-900 text-white rounded-xl font-bold flex items-center gap-2 hover:bg-slate-800 transition-all shadow-sm shadow-slate-200 cursor-pointer">
            <Upload size={16} />
            Upload Source
          </button>
        </div>

        <div className="grid grid-cols-12 gap-6">
          {/* Active Intelligence Assets Card */}
          <div className="col-span-4 bg-white border border-slate-200 rounded-2xl p-6 shadow-sm flex flex-col gap-4">
            <div className="flex items-center gap-2 text-[11px] font-bold text-slate-400 uppercase tracking-wider">
              <Database size={14} />
              Active Intelligence Assets
            </div>
            <div>
              <div className="flex items-baseline gap-2">
                <span className="text-4xl font-bold text-slate-900">42</span>
                <span className="text-sm font-bold text-emerald-600 flex items-center gap-0.5">
                  <Plus size={12} /> 3 this week
                </span>
              </div>
              <p className="text-sm text-slate-500 mt-2 leading-relaxed">
                Providing context across 5 distinct AI agent workflows.
              </p>
            </div>
          </div>

          {/* Agent Grounding Matrix Card */}
          <div className="col-span-8 bg-white border border-slate-200 rounded-2xl p-6 shadow-sm flex flex-col gap-4 relative">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-[11px] font-bold text-slate-400 uppercase tracking-wider">
                <Bot size={14} />
                Agent Grounding Matrix
              </div>
              <button className="text-[11px] font-bold text-blue-600 uppercase tracking-wider hover:underline cursor-pointer">
                Configure All
              </button>
            </div>
            
            <div className="flex items-center gap-4 mt-2">
              <div className="flex-1 bg-slate-50 border border-slate-100 rounded-xl p-4 flex flex-col gap-3 group hover:border-blue-200 transition-all cursor-pointer">
                <div className="flex items-center justify-between">
                  <h4 className="font-bold text-slate-900 flex items-center gap-2">
                    <ShieldCheck size={16} className="text-blue-500" />
                    Rx Verification
                  </h4>
                </div>
                <div className="flex flex-wrap gap-2">
                  <span className="px-2 py-1 bg-white border border-slate-200 rounded text-[10px] font-medium text-slate-600">DrugDB_v2</span>
                  <span className="px-2 py-1 bg-white border border-slate-200 rounded text-[10px] font-medium text-slate-600">Interactions</span>
                </div>
              </div>

              <div className="flex-1 bg-slate-50 border border-slate-100 rounded-xl p-4 flex flex-col gap-3 group hover:border-blue-200 transition-all cursor-pointer">
                <div className="flex items-center justify-between">
                  <h4 className="font-bold text-slate-900 flex items-center gap-2">
                    <Activity size={16} className="text-blue-500" />
                    Triage Assistant
                  </h4>
                </div>
                <div className="flex flex-wrap gap-2">
                  <span className="px-2 py-1 bg-white border border-slate-200 rounded text-[10px] font-medium text-slate-600">Fall_Risk</span>
                  <span className="px-2 py-1 bg-white border border-slate-200 rounded text-[10px] font-medium text-slate-600">Guidelines_v4</span>
                </div>
              </div>

              <div className="flex-1 border-2 border-dashed border-slate-200 rounded-xl p-4 flex flex-col items-center justify-center gap-2 group hover:border-blue-300 hover:bg-blue-50/30 transition-all cursor-pointer">
                <Plus size={20} className="text-slate-300 group-hover:text-blue-500 transition-colors" />
                <span className="text-xs font-bold text-slate-400 group-hover:text-blue-600">New Agent Rule</span>
              </div>
            </div>
          </div>
        </div>

        <div className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden mt-2">
          <div className="p-5 border-b border-slate-100 flex items-center justify-between bg-slate-50/30">
            <h3 className="font-bold text-slate-900">Data Sources</h3>
            <div className="flex items-center gap-3">
              <div className="relative">
                <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                <input 
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Filter sources..."
                  className="pl-9 pr-4 py-1.5 bg-white border border-slate-200 rounded-lg text-xs focus:outline-none focus:ring-2 focus:ring-blue-100 transition-all"
                />
              </div>
              <select 
                value={typeFilter}
                onChange={(e) => setTypeFilter(e.target.value)}
                className="bg-white border border-slate-200 rounded-lg px-3 py-1.5 text-xs font-medium text-slate-600 focus:outline-none focus:ring-2 focus:ring-blue-100 cursor-pointer"
              >
                <option>All Source Types</option>
                <option>PDF Documents</option>
                <option>CSV Databases</option>
              </select>
            </div>
          </div>

          <table className="w-full text-left">
            <thead>
              <tr className="bg-slate-50/50 border-b border-slate-100">
                <th className="px-6 py-4 text-[11px] font-bold text-slate-400 uppercase tracking-wider">Source Name & Type</th>
                <th className="px-6 py-4 text-[11px] font-bold text-slate-400 uppercase tracking-wider">Status</th>
                <th className="px-6 py-4 text-[11px] font-bold text-slate-400 uppercase tracking-wider">Assigned Agents</th>
                <th className="px-6 py-4 text-[11px] font-bold text-slate-400 uppercase tracking-wider">Last Indexed</th>
                <th className="px-6 py-4 text-[11px] font-bold text-slate-400 uppercase tracking-wider text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filteredSources.map((source, i) => (
                <tr key={i} className="hover:bg-slate-50/50 transition-colors group">
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-3">
                      <div className="w-9 h-9 bg-slate-50 border border-slate-100 rounded-lg flex items-center justify-center text-slate-400 group-hover:text-blue-500 transition-colors">
                        {source.type === "PDF" ? <FileText size={18} /> : <FileSpreadsheet size={18} />}
                      </div>
                      <div>
                        <h4 className="font-bold text-slate-900 text-sm group-hover:text-blue-600 transition-colors">{source.name}</h4>
                        <p className="text-xs text-slate-500 font-mono">{source.file}</p>
                      </div>
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-wider ${
                      source.error ? 'bg-red-50 text-red-600' : 'bg-blue-50 text-blue-600'
                    }`}>
                      {source.error ? <AlertCircle size={10} /> : <ShieldCheck size={10} />}
                      {source.status}
                    </span>
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex -space-x-2">
                      {source.agents.length > 0 ? source.agents.map((agent, j) => (
                        <div key={j} className="w-7 h-7 rounded-full bg-slate-100 border-2 border-white flex items-center justify-center text-[10px] font-bold text-slate-600" title={agent}>
                          {agent}
                        </div>
                      )) : (
                        <span className="text-xs italic text-slate-400">Unassigned</span>
                      )}
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex flex-col">
                      <span className="text-sm font-medium text-slate-700">{source.date}</span>
                      <span className="text-[10px] text-slate-400 font-mono">{source.time}</span>
                    </div>
                  </td>
                  <td className="px-6 py-4 text-right">
                    {source.error ? (
                      <button className="text-xs font-bold text-blue-600 hover:underline cursor-pointer flex items-center gap-1 justify-end ml-auto">
                        <RefreshCw size={12} />
                        Retry
                      </button>
                    ) : (
                      <button className="text-slate-300 hover:text-slate-600 transition-colors cursor-pointer">
                        <MoreHorizontal size={18} />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          
          <div className="px-6 py-4 bg-slate-50/30 border-t border-slate-100 flex items-center justify-between">
            <span className="text-xs text-slate-500 font-medium">Showing 1 to {DATA_SOURCES.length} of 42 entries</span>
            <div className="flex items-center gap-2">
              <button className="p-1.5 border border-slate-200 rounded-lg text-slate-400 hover:bg-white hover:text-slate-600 transition-all disabled:opacity-50 cursor-pointer">
                <ChevronRight size={16} className="rotate-180" />
              </button>
              <button className="p-1.5 border border-slate-200 rounded-lg text-slate-400 hover:bg-white hover:text-slate-600 transition-all cursor-pointer">
                <ChevronRight size={16} />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
