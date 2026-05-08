import { useState } from "react";
import { 
  Filter, Search, ChevronDown, Download, ChevronRight, 
  ArrowLeft, Clock, History, Edit3, AlertTriangle, 
  Activity, Heart, Pill, CheckCircle2, MessageSquare, 
  Send, Mic, User, Bot, Info, Zap, Plus, ShieldCheck, 
  MoreHorizontal
} from "lucide-react";
import { useOutletContext } from "react-router-dom";

type OutletContext = {
  isPrivacyMode: boolean;
};

const MOCK_PATIENTS = [
  { id: "P-8834", name: "Thomas Miller", age: "72M", riskLevel: "High", adherence: 42, lastInteraction: "Oct 12, 09:15 AM", protocol: "Cardio-01", mrn: "882-12-4401", admission: "Oct 12, 2023" },
  { id: "P-7219", name: "Eleanor Vance", age: "68F", riskLevel: "Elevated", adherence: 78, lastInteraction: "Oct 11, 14:30 PM", protocol: "Endo-04", mrn: "993-45-8812", admission: "Oct 11, 2023" },
  { id: "P-9021", name: "James Wilson", age: "55M", riskLevel: "Stable", adherence: 98, lastInteraction: "Oct 10, 08:45 AM", protocol: "Resp-02", mrn: "441-90-2231", admission: "Oct 10, 2023" },
  { id: "P-4451", name: "Sarah Connor", age: "44F", riskLevel: "Stable", adherence: 85, lastInteraction: "Oct 09, 11:20 AM", protocol: "Neuro-01", mrn: "112-88-3342", admission: "Oct 09, 2023" },
  { id: "P-1122", name: "Robert Drake", age: "29M", riskLevel: "Stable", adherence: 92, lastInteraction: "2h ago", protocol: "Immuno-02", mrn: "221-33-4455", admission: "Oct 13, 2023" },
  { id: "P-3344", name: "Maria Garcia", age: "61F", riskLevel: "High", adherence: 55, lastInteraction: "15m ago", protocol: "Cardio-01", mrn: "554-22-1188", admission: "Oct 14, 2023" },
  { id: "P-5566", name: "Chen Wei", age: "48M", riskLevel: "Elevated", adherence: 71, lastInteraction: "5h ago", protocol: "Onco-01", mrn: "998-11-2233", admission: "Oct 15, 2023" },
  { id: "P-7788", name: "Linda Smith", age: "82F", riskLevel: "Stable", adherence: 96, lastInteraction: "1d ago", protocol: "Geri-04", mrn: "112-22-3344", admission: "Oct 16, 2023" },
  { id: "P-9900", name: "Ahmed Khan", age: "35M", riskLevel: "Elevated", adherence: 68, lastInteraction: "3h ago", protocol: "Infec-01", mrn: "445-55-6677", admission: "Oct 17, 2023" },
  { id: "P-1011", name: "Sophie Laurent", age: "24F", riskLevel: "Stable", adherence: 100, lastInteraction: "6h ago", protocol: "Psych-02", mrn: "887-77-6655", admission: "Oct 18, 2023" },
  { id: "P-1213", name: "David Kim", age: "52M", riskLevel: "High", adherence: 38, lastInteraction: "10m ago", protocol: "Renal-01", mrn: "221-44-3322", admission: "Oct 19, 2023" },
  { id: "P-1415", name: "Elena Rossi", age: "41F", riskLevel: "Stable", adherence: 88, lastInteraction: "4h ago", protocol: "Derma-01", mrn: "665-44-1122", admission: "Oct 20, 2023" },
  { id: "P-1617", name: "John Adams", age: "65M", riskLevel: "Elevated", adherence: 75, lastInteraction: "2h ago", protocol: "Cardio-01", mrn: "112-99-8877", admission: "Oct 21, 2023" },
  { id: "P-1819", name: "Yuki Tanaka", age: "31F", riskLevel: "Stable", adherence: 94, lastInteraction: "1h ago", protocol: "Endo-02", mrn: "332-11-5544", admission: "Oct 22, 2023" },
];

export default function PatientManagementPage() {
  const { isPrivacyMode } = useOutletContext<OutletContext>();
  const [selectedPatientId, setSelectedPatientId] = useState<string | null>("P-7219");
  const [activeProfileTab, setActiveProfileTab] = useState<"patient" | "reasoning">("patient");

  const [searchQuery, setSearchQuery] = useState("");
  const [riskFilter, setRiskFilter] = useState<string>("All");
  const [showFilterMenu, setShowFilterMenu] = useState(false);

  const filteredPatients = MOCK_PATIENTS.filter(p => {
    const matchesSearch = p.name.toLowerCase().includes(searchQuery.toLowerCase()) || 
                          p.id.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesRisk = riskFilter === "All" || p.riskLevel === riskFilter;
    return matchesSearch && matchesRisk;
  });

  const selectedPatient = MOCK_PATIENTS.find(p => p.id === selectedPatientId) || MOCK_PATIENTS[1];
  const maskedName = selectedPatient.name.split(" ")[0] + " " + selectedPatient.name.split(" ")[1]?.[0] + ".";

  return (
    <div className="flex h-full overflow-hidden bg-slate-50/50">
      {/* Left Column: Patient Directory (Master) */}
      <div className="w-[450px] border-r border-slate-200 bg-white flex flex-col shrink-0 overflow-hidden">
        <div className="p-6 border-b border-slate-100 flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-bold text-slate-900 tracking-tight">Patient Directory</h2>
            <div className="flex gap-2 relative">
              <button 
                onClick={() => setShowFilterMenu(!showFilterMenu)}
                className={`p-2 border border-slate-200 rounded-lg transition-all cursor-pointer ${riskFilter !== 'All' ? 'bg-blue-600 text-white border-blue-600' : 'text-slate-400 hover:text-slate-600 hover:bg-slate-50'}`}
              >
                <Filter size={16} />
              </button>
              {showFilterMenu && (
                <div className="absolute top-10 right-0 w-48 bg-white border border-slate-200 rounded-xl shadow-xl z-50 py-2 overflow-hidden animate-in fade-in zoom-in duration-200">
                  <p className="px-4 py-2 text-[10px] font-black text-slate-400 uppercase tracking-widest border-b border-slate-50 mb-1">Filter by Risk</p>
                  {["All", "High", "Elevated", "Stable"].map((level) => (
                    <button
                      key={level}
                      onClick={() => { setRiskFilter(level); setShowFilterMenu(false); }}
                      className={`w-full px-4 py-2 text-sm text-left hover:bg-slate-50 transition-colors flex items-center justify-between font-medium ${riskFilter === level ? 'text-blue-600 bg-blue-50/50' : 'text-slate-600'}`}
                    >
                      {level}
                      {riskFilter === level && <CheckCircle2 size={14} />}
                    </button>
                  ))}
                </div>
              )}
              <button className="p-2 border border-slate-200 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-50 transition-all cursor-pointer">
                <Download size={16} />
              </button>
            </div>
          </div>
          <div className="relative">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input 
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search patients..." 
              className="w-full pl-9 pr-4 py-2 bg-slate-50 border border-slate-100 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-100 focus:border-blue-500 transition-all"
            />
          </div>
        </div>

        <div className="flex-1 overflow-y-auto">
          <div className="divide-y divide-slate-100">
            {filteredPatients.length > 0 ? (
              filteredPatients.map((p) => (
                <div 
                  key={p.id}
                  onClick={() => setSelectedPatientId(p.id)}
                  className={`p-4 flex flex-col gap-3 cursor-pointer transition-all hover:bg-slate-50/80 ${selectedPatientId === p.id ? "bg-blue-50/50 border-r-2 border-blue-600" : ""}`}
                >
                  <div className="flex justify-between items-start">
                    <div className="flex flex-col">
                      <span className="font-mono text-[10px] font-bold text-blue-600 uppercase tracking-widest">{p.id}</span>
                      <span className={`text-sm font-bold ${isPrivacyMode ? "blur-sm" : "text-slate-900"}`}>{p.name}</span>
                    </div>
                    <span className={`px-2 py-0.5 rounded text-[9px] font-black uppercase tracking-tighter ${
                      p.riskLevel === 'High' ? 'bg-red-600 text-white shadow-sm shadow-red-200' : 
                      p.riskLevel === 'Elevated' ? 'bg-blue-50 text-blue-700 border border-blue-100' : 
                      'bg-slate-50 text-slate-500 border border-slate-200'
                    }`}>
                      {p.riskLevel}
                    </span>
                  </div>
                  <div className="flex items-center justify-between text-[10px] font-medium text-slate-400">
                    <div className="flex items-center gap-1.5">
                      <Clock size={10} />
                      {p.lastInteraction}
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-slate-900 font-bold">{p.adherence}% Adherence</span>
                      <div className="w-12 h-1.5 bg-slate-100 rounded-full overflow-hidden">
                        <div 
                          className={`h-full ${p.adherence < 70 ? 'bg-red-600' : p.adherence < 85 ? 'bg-slate-400' : 'bg-slate-900'}`}
                          style={{ width: `${p.adherence}%` }}
                        />
                      </div>
                    </div>
                  </div>
                </div>
              ))
            ) : (
              <div className="p-12 text-center">
                <Search size={32} className="text-slate-200 mx-auto mb-4" />
                <p className="text-sm font-bold text-slate-400 uppercase tracking-wider">No Patients Found</p>
                <button 
                  onClick={() => { setSearchQuery(""); setRiskFilter("All"); }}
                  className="mt-2 text-xs font-bold text-blue-600 hover:underline cursor-pointer"
                >
                  Reset Filters
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Right Column: Patient Profile (Detail) */}
      <div className="flex-1 flex flex-col overflow-hidden bg-white">
        <div className="p-8 border-b border-slate-100 flex items-center justify-between shrink-0">
          <div className="flex flex-col">
            <div className="flex items-center gap-2 text-[10px] font-bold tracking-widest text-slate-400 uppercase mb-1">
              <span>Directory</span>
              <ChevronRight size={12} />
              <span className="text-blue-600">{selectedPatient.id}</span>
            </div>
            <h1 className={`text-2xl font-bold text-slate-900 tracking-tight ${isPrivacyMode ? "blur-sm" : ""}`}>
              {isPrivacyMode ? maskedName : selectedPatient.name}, {selectedPatient.age}
            </h1>
            <p className="text-sm text-slate-500">MRN: {selectedPatient.mrn} • Admitted: {selectedPatient.admission}</p>
          </div>
          <div className="flex gap-3">
            <button className="px-4 py-2 bg-white border border-slate-200 text-slate-700 rounded-xl font-bold hover:bg-slate-50 transition-all shadow-sm flex items-center gap-2 text-sm cursor-pointer">
              <History size={16} />
              Clinical History
            </button>
            <button className="px-4 py-2 bg-slate-900 text-white rounded-xl font-bold hover:bg-slate-800 transition-all shadow-sm flex items-center gap-2 text-sm cursor-pointer">
              <Edit3 size={16} />
              Update Protocol
            </button>
          </div>
        </div>

        <div className="flex-1 flex overflow-hidden">
          {/* Central Workspace Scrollable */}
          <div className="flex-1 overflow-y-auto p-8 flex flex-col gap-6">
            {/* High Severity Alert */}
            {selectedPatient.riskLevel === "High" && (
              <div className="bg-white border border-slate-200 rounded-2xl p-5 flex items-start gap-4 shadow-sm group">
                <div className="w-10 h-10 bg-slate-50 border border-slate-100 rounded-xl flex items-center justify-center shrink-0">
                  <AlertTriangle size={20} className="text-red-600" />
                </div>
                <div className="flex-1">
                  <div className="flex items-center justify-between mb-1">
                    <div className="flex items-center gap-3">
                      <p className="font-bold text-slate-900">Dizziness Reported</p>
                      <span className="px-2 py-0.5 bg-red-600 text-white text-[9px] font-black uppercase tracking-tighter rounded-sm shadow-sm shadow-red-200">
                        High Severity
                      </span>
                    </div>
                    <button className="text-[11px] font-bold text-red-600 hover:text-red-700 uppercase tracking-wider cursor-pointer">Acknowledge</button>
                  </div>
                  <p className="text-sm text-slate-600 leading-relaxed">
                    AI Agent logged a patient report of "room spinning upon standing" at 08:45 AM. 
                    Potential interaction with recently increased Lisinopril dose.
                  </p>
                </div>
              </div>
            )}

            {/* Clinical Flags Grid */}
            <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
              <div className="flex items-center gap-2 mb-6">
                <Activity size={18} className="text-slate-400" />
                <h3 className="font-bold text-slate-900">Clinical Flags</h3>
              </div>
              <div className="space-y-4">
                {[
                  { level: "High", title: "Orthostatic Hypotension Risk", reasoning: "Patient reported 'spinning' shortly after morning dose. Suggests postural drop exacerbated by concurrent therapy." },
                  { level: "Medium", title: "Fall Risk Elevation", reasoning: "Acute dizziness combined with age (68F) increases immediate risk. Requires counseling before ambulation." },
                  { level: "Low", title: "Routine Adherence", reasoning: "Patient confirmed taking medication promptly at 8:00 AM." }
                ].map((flag, i) => (
                  <div key={i} className="p-4 bg-slate-50 border border-slate-100 rounded-xl space-y-2">
                    <div className="flex items-center gap-3">
                      <span className={`px-2 py-0.5 rounded text-[9px] font-black uppercase tracking-tighter ${
                        flag.level === 'High' ? 'bg-red-600 text-white shadow-sm' : 
                        flag.level === 'Medium' ? 'bg-slate-900 text-white' : 
                        'bg-slate-200 text-slate-600'
                      }`}>
                        {flag.level}
                      </span>
                      <span className="text-sm font-bold text-slate-900">{flag.title}</span>
                    </div>
                    <p className="text-xs text-slate-600 leading-relaxed"><span className="font-bold text-slate-400 uppercase text-[9px] mr-2">Reasoning:</span>{flag.reasoning}</p>
                  </div>
                ))}
              </div>
            </div>

            {/* AI Direction & Objectives */}
            <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
              <div className="flex items-center justify-between mb-6">
                <div className="flex items-center gap-2">
                  <Zap size={18} className="text-slate-400" />
                  <h3 className="font-bold text-slate-900">AI Direction & Objectives</h3>
                </div>
                <span className="px-2 py-1 bg-slate-900 text-white text-[10px] font-bold uppercase rounded tracking-wider">Cycle: Day 4/14</span>
              </div>
              <div className="space-y-6">
                <div>
                  <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-3">Current Cycle Objectives</p>
                  <div className="bg-slate-50 border border-slate-100 rounded-xl p-4 space-y-3">
                    {["Monitor for ACE-inhibitor induced dry cough.", "Assess morning blood pressure adherence."].map((obj, i) => (
                      <div key={i} className="flex items-center gap-3">
                        <input type="checkbox" checked readOnly className="w-4 h-4 rounded border-slate-300 text-slate-900 focus:ring-slate-500" />
                        <span className="text-sm text-slate-700 font-medium">{obj}</span>
                      </div>
                    ))}
                    <div className="relative mt-2">
                      <input placeholder="Add new objective..." className="w-full pl-4 pr-10 py-2 bg-white border border-slate-200 rounded-lg text-xs focus:ring-2 focus:ring-blue-100 transition-all" />
                      <button className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-blue-600 transition-colors cursor-pointer"><Plus size={14} /></button>
                    </div>
                  </div>
                </div>
                <div>
                  <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-3">Subsequent Agent Instructions (Mid-Cycle Update)</p>
                  <textarea 
                    className="w-full p-4 bg-slate-50 border border-slate-200 rounded-xl text-sm min-h-[100px] focus:ring-2 focus:ring-blue-100 transition-all"
                    defaultValue="Given reports of dizziness, prioritize asking about orthostatic hypotension symptoms. If confirmed, recommend holding next Amlodipine dose."
                  />
                  <div className="flex justify-end mt-4">
                    <button className="px-6 py-2.5 bg-slate-900 text-white rounded-xl font-bold flex items-center gap-2 hover:bg-slate-800 transition-all shadow-md shadow-slate-200 cursor-pointer">
                      <Send size={16} />
                      Deploy to Agent
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Right Sidebar: Interaction Log */}
          <div className="w-[400px] border-l border-slate-100 flex flex-col shrink-0 overflow-hidden">
            <div className="p-4 border-b border-slate-100 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <MessageSquare size={16} className="text-slate-400" />
                <h3 className="font-bold text-slate-900 text-sm">Interaction Log</h3>
              </div>
              <div className="flex items-center gap-1.5">
                <div className="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-pulse" />
                <span className="text-[9px] font-bold text-slate-400 uppercase tracking-wider">Agent Idle</span>
              </div>
            </div>
            
            <div className="p-1 bg-slate-100 mx-4 mt-4 rounded-lg flex gap-1">
              <button 
                onClick={() => setActiveProfileTab("patient")}
                className={`flex-1 py-1.5 text-[10px] font-bold rounded-md transition-all cursor-pointer ${activeProfileTab === "patient" ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-700"}`}
              >
                Patient Facing
              </button>
              <button 
                onClick={() => setActiveProfileTab("reasoning")}
                className={`flex-1 py-1.5 text-[10px] font-bold rounded-md transition-all cursor-pointer ${activeProfileTab === "reasoning" ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-700"}`}
              >
                Agent Reasoning
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-6">
              {activeProfileTab === "patient" ? (
                <>
                  <div className="flex justify-center"><span className="text-[9px] font-bold text-slate-300 uppercase tracking-widest">Today, 08:42 AM</span></div>
                  <div className="flex gap-3">
                    <div className="w-8 h-8 rounded-lg bg-slate-900 flex items-center justify-center shrink-0"><Bot size={18} className="text-white" /></div>
                    <div className="bg-slate-100 rounded-2xl rounded-tl-none p-3 max-w-[85%]"><p className="text-sm text-slate-700 leading-relaxed">Good morning, Eleanor. How are you feeling today?</p></div>
                  </div>
                  <div className="flex gap-3 flex-row-reverse">
                    <div className="w-8 h-8 rounded-lg bg-blue-100 flex items-center justify-center shrink-0"><span className="text-[9px] font-bold text-blue-600">EV</span></div>
                    <div className="bg-blue-600 text-white rounded-2xl rounded-tr-none p-3 max-w-[85%]"><p className="text-sm leading-relaxed">I'm feeling very dizzy today. The room was spinning.</p></div>
                  </div>
                  <div className="bg-blue-50 border border-blue-100 rounded-xl p-3 ml-11">
                    <div className="flex items-center gap-2 mb-1"><Info size={14} className="text-blue-400" /><span className="text-[9px] font-bold text-blue-600 uppercase tracking-wider">Inner Reasoning Triggered</span></div>
                    <p className="text-[11px] text-blue-800 leading-relaxed italic">Patient reports vertigo. High severity adverse event. Escalate to Pharmacist.</p>
                  </div>
                </>
              ) : (
                <div className="space-y-4">
                  {[
                    { time: "08:42:10", type: "Extraction", text: "Identified 'dizzy' as a potential Symptom Flag.", confidence: 0.98 },
                    { time: "08:42:15", type: "Policy Check", text: "Cross-referencing Protocol Cardio-01 (Lisinopril).", confidence: 1.0 },
                    { time: "08:42:22", type: "Safety Guard", text: "Matched 'spinning' with Orthostatic Hypotension risk patterns.", confidence: 0.92 },
                    { time: "08:42:25", type: "Action", text: "Decision: Escalate to Pharmacist; Set High Severity.", confidence: 1.0 }
                  ].map((log, i) => (
                    <div key={i} className="p-3 border border-slate-100 rounded-xl bg-slate-50/50 space-y-1.5">
                      <div className="flex items-center justify-between">
                        <span className="text-[10px] font-mono text-slate-400">{log.time}</span>
                        <span className="px-1.5 py-0.5 bg-slate-200 text-slate-600 text-[8px] font-bold uppercase rounded tracking-wider">{log.type}</span>
                      </div>
                      <p className="text-xs text-slate-700 font-medium">{log.text}</p>
                      <div className="flex items-center gap-2">
                        <div className="flex-1 h-1 bg-slate-200 rounded-full overflow-hidden">
                          <div className="h-full bg-blue-600" style={{ width: `${log.confidence * 100}%` }} />
                        </div>
                        <span className="text-[9px] font-bold text-slate-400">{(log.confidence * 100).toFixed(0)}%</span>
                      </div>
                    </div>
                  ))}
                  <div className="mt-4 p-3 bg-blue-50 border border-blue-100 rounded-xl">
                    <p className="text-[10px] font-bold text-blue-600 uppercase tracking-widest mb-2">Grounding Context</p>
                    <p className="text-[11px] text-blue-800 leading-relaxed">
                      Lisinopril 20mg dose increased 48h ago. Common SE includes postural hypotension. 
                      Evidence: Lexicomp (Horton et al., 2022).
                    </p>
                  </div>
                </div>
              )}
            </div>

            <div className="p-4 border-t border-slate-100">
              <div className="flex gap-2">
                <input placeholder="Override message..." className="flex-1 pl-4 pr-4 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs focus:ring-2 focus:ring-blue-100 transition-all" />
                <button className="w-8 h-8 bg-slate-100 text-slate-400 rounded-lg flex items-center justify-center hover:bg-slate-200 hover:text-slate-600 transition-all cursor-pointer"><Mic size={14} /></button>
                <button className="w-8 h-8 bg-slate-900 text-white rounded-lg flex items-center justify-center hover:bg-slate-800 transition-all cursor-pointer"><Send size={14} /></button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
