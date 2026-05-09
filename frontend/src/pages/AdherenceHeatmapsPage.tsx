import { ChevronDown, Calendar, Search, AlertTriangle, Zap, Activity } from "lucide-react";
import { useState } from "react";
import { useOutletContext } from "react-router-dom";

type OutletContext = {
  isPrivacyMode: boolean;
};

// Generate 30 days of mock data
const generateMockHeatmapData = () => {
  const patients = [
    { id: "P-4492", name: "Jameson, M.", isCritical: true },
    { id: "P-8821", name: "Chen, L.", isCritical: false },
    { id: "P-1102", name: "Smith, A.", isCritical: false },
    { id: "P-3345", name: "Garcia, R.", isCritical: true },
    { id: "P-9910", name: "Okafor, E.", isCritical: false },
    { id: "P-5521", name: "Davis, S.", isCritical: false },
    { id: "P-7734", name: "Miller, T.", isCritical: true },
    { id: "P-2219", name: "Wilson, B.", isCritical: false },
  ];

  return patients.map(pt => ({
    ...pt,
    history: Array.from({ length: 30 }, (_, i) => {
      // Create some realistic patterns
      if (pt.isCritical && i > 25) return 'missed'; // Recent consecutive misses
      if (pt.id === "P-8821" && i % 7 === 0) return 'missed'; // Weekend misses
      
      const rand = Math.random();
      if (rand > 0.9) return 'missed';
      if (rand < 0.05) return 'nodata';
      return 'taken';
    })
  }));
};

const MOCK_HEATMAP_DATA = generateMockHeatmapData();

export default function AdherenceHeatmapsPage() {
  const { isPrivacyMode } = useOutletContext<OutletContext>();
  const [protocolFilter, setProtocolFilter] = useState("All Protocols");
  const [sortBy, setSortBy] = useState("Risk (Highest First)");
  const [searchTerm, setSearchTerm] = useState("");
  
  const days = Array.from({ length: 30 }, (_, i) => 30 - i); // 30 down to 1

  const filteredData = MOCK_HEATMAP_DATA.filter(pt => 
    (protocolFilter === "All Protocols" || pt.id === "P-4492") && // Simplified mock filter
    (pt.id.toLowerCase().includes(searchTerm.toLowerCase()) || pt.name.toLowerCase().includes(searchTerm.toLowerCase()))
  );

  const sortedData = [...filteredData].sort((a, b) => {
    if (sortBy === "Risk (Highest First)") {
      return (b.isCritical ? 1 : 0) - (a.isCritical ? 1 : 0);
    }
    if (sortBy === "Patient ID") {
      return a.id.localeCompare(b.id);
    }
    if (sortBy === "Adherence (Lowest First)") {
      const aMissed = a.history.filter(h => h === 'missed').length;
      const bMissed = b.history.filter(h => h === 'missed').length;
      return bMissed - aMissed;
    }
    return 0;
  });

  return (
    <div className="h-full overflow-y-auto p-8 bg-[#F5F5F6]">
      <div className="flex flex-col gap-6 w-full">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-bold tracking-tight text-slate-900 mb-1">Adherence Heatmaps</h2>
            <p className="text-sm text-slate-500 font-medium">Longitudinal analysis of patient compliance and medication signaling.</p>
          </div>
          <div className="flex gap-2">
            <button className="px-3 py-1.5 bg-white border border-slate-200 text-slate-500 rounded-lg text-[11px] font-bold uppercase tracking-wider hover:bg-slate-50 hover:text-slate-900 transition-all flex items-center gap-2 cursor-pointer">
              <Calendar size={14} />
              Last 30 Days <ChevronDown size={12} />
            </button>
            <button className="px-3 py-1.5 bg-white border border-slate-200 text-slate-500 rounded-lg text-[11px] font-bold uppercase tracking-wider hover:bg-slate-50 hover:text-slate-900 transition-all flex items-center gap-2 cursor-pointer">
              Export
            </button>
          </div>
        </div>

        <div className="flex gap-6 items-start">
          <div className="flex-1 flex flex-col gap-4">
            {/* Controls Card */}
            <div className="bg-white border border-slate-200 rounded-2xl shadow-sm p-4 flex items-center justify-between">
              <div className="flex items-center gap-4">
                <div className="relative w-64">
                  <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                  <input 
                    type="text" 
                    placeholder="Search Patient ID or Name..." 
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    className="w-full pl-9 pr-4 py-1.5 bg-slate-50 border border-slate-200 rounded-lg text-xs focus:outline-none focus:ring-2 focus:ring-blue-100 transition-all"
                  />
                </div>
                <div className="h-6 w-px bg-slate-100 mx-2" />
                <div className="flex gap-4">
                  <div className="flex items-center gap-2">
                    <label className="text-[10px] font-bold tracking-wider text-slate-400 uppercase">Protocol</label>
                    <select 
                      value={protocolFilter}
                      onChange={(e) => setProtocolFilter(e.target.value)}
                      className="bg-white border border-slate-200 rounded-lg px-2 py-1 text-[11px] font-bold outline-none cursor-pointer focus:ring-2 focus:ring-blue-100 transition-all"
                    >
                      <option>All Protocols</option>
                      <option>Cardio-01</option>
                      <option>Neuro-04</option>
                    </select>
                  </div>
                  <div className="flex items-center gap-2">
                    <label className="text-[10px] font-bold tracking-wider text-slate-400 uppercase">Sort</label>
                    <select 
                      value={sortBy}
                      onChange={(e) => setSortBy(e.target.value)}
                      className="bg-white border border-slate-200 rounded-lg px-2 py-1 text-[11px] font-bold outline-none cursor-pointer focus:ring-2 focus:ring-blue-100 transition-all"
                    >
                      <option>Risk (Highest First)</option>
                      <option>Adherence (Lowest First)</option>
                      <option>Patient ID</option>
                    </select>
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-4 bg-slate-50 border border-slate-100 rounded-lg px-4 py-2">
                <div className="flex items-center gap-2">
                  <div className="w-2.5 h-2.5 rounded-[2px] bg-blue-600"></div>
                  <span className="text-[9px] font-bold tracking-wider text-slate-500 uppercase">Taken</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-2.5 h-2.5 rounded-[2px] bg-red-500"></div>
                  <span className="text-[9px] font-bold tracking-wider text-slate-500 uppercase">Missed</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-2.5 h-2.5 rounded-[2px] bg-slate-200"></div>
                  <span className="text-[9px] font-bold tracking-wider text-slate-500 uppercase">No Data</span>
                </div>
              </div>
            </div>

            {/* Heatmap Card */}
            <div className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden p-6">
              <div className="overflow-x-auto">
                <div className="min-w-max">
                  <div className="flex items-center mb-6 pl-32">
                    {days.map(day => (
                      <div key={day} className={`w-4 mx-0.5 text-center text-[10px] font-bold ${day % 7 === 0 || day % 7 === 1 ? 'text-blue-500' : 'text-slate-400'}`}>
                        {day % 5 === 0 || day === 1 ? day : ''}
                      </div>
                    ))}
                  </div>

                  <div className="flex flex-col gap-3 relative">
                    {/* Weekend Indicators (Stripes) */}
                    <div className="absolute top-0 bottom-0 left-32 right-0 pointer-events-none flex">
                      {days.map((day, idx) => (
                        <div 
                          key={idx} 
                          className={`w-4 mx-0.5 ${day % 7 === 0 || day % 7 === 1 ? 'bg-slate-50/40' : ''}`}
                        />
                      ))}
                    </div>

                    {sortedData.map((pt) => (
                      <div key={pt.id} className="flex items-center group relative z-10">
                        <div className="w-32 shrink-0 pr-4 flex items-center justify-between">
                          <div className="flex flex-col">
                            <span className={`font-mono text-xs font-bold transition-colors ${pt.isCritical ? 'text-red-600' : 'text-slate-900'}`}>
                              {pt.id}
                            </span>
                            <span className="text-[9px] font-bold text-slate-400 uppercase tracking-tight truncate w-20">{pt.name}</span>
                          </div>
                          {pt.isCritical && <AlertTriangle size={12} className="text-red-500 animate-pulse" />}
                        </div>
                        <div className="flex bg-white group-hover:bg-slate-50 p-1 rounded-lg border border-transparent group-hover:border-slate-100 transition-all">
                          {pt.history.map((status, i) => (
                            <div 
                              key={i} 
                              className={`w-4 h-7 mx-0.5 rounded-[3px] hover:opacity-80 transition-all cursor-crosshair hover:scale-y-110 active:scale-95 ${
                                status === 'taken' ? 'bg-blue-600' :
                                status === 'missed' ? 'bg-red-500' : 'bg-slate-100'
                              }`}
                              title={`Day ${30-i}: ${status.toUpperCase()}`}
                            />
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Intervention Sidebar */}
          <div className="w-80 shrink-0 flex flex-col gap-4">
            <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
              <div className="flex items-center justify-between mb-6 border-b border-slate-100 pb-4">
                <div className="flex items-center gap-2">
                  <Activity size={18} className="text-red-500" />
                  <h3 className="font-bold text-slate-900">Interventions</h3>
                </div>
                <span className="w-5 h-5 bg-red-600 text-white text-[10px] font-bold flex items-center justify-center rounded-full">2</span>
              </div>
              
              <div className="flex flex-col gap-4">
                <div className="bg-white rounded-2xl p-4 border border-slate-100 hover:border-red-200 transition-all group">
                  <div className="flex justify-between items-start mb-3">
                    <div className="flex flex-col">
                      <span className="font-mono text-sm font-bold text-slate-900">P-4492</span>
                      <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Jameson, M.</span>
                    </div>
                    <span className="bg-red-50 text-red-600 px-2 py-1 rounded-lg text-[9px] font-black uppercase tracking-wider border border-red-100 shadow-sm">Critical</span>
                  </div>
                  <p className="text-xs text-slate-600 leading-relaxed font-medium mb-4">Consecutive missed doses of Apixaban detected over last 72h. High bleeding risk protocol active.</p>
                  <button className="w-full py-2 bg-slate-100 text-slate-700 rounded-lg text-[10px] font-bold uppercase tracking-wider hover:bg-slate-900 hover:text-white transition-all flex items-center justify-center gap-2">
                    Review Protocol
                  </button>
                </div>

                <div className="bg-white rounded-2xl p-4 border border-slate-100 hover:border-blue-200 transition-all group">
                  <div className="flex justify-between items-start mb-3">
                    <div className="flex flex-col">
                      <span className="font-mono text-sm font-bold text-slate-900">P-7734</span>
                      <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Miller, T.</span>
                    </div>
                    <span className="bg-blue-50 text-blue-600 px-2 py-1 rounded-lg text-[9px] font-black uppercase tracking-wider border border-blue-100 shadow-sm">Analysis</span>
                  </div>
                  <p className="text-xs text-slate-600 leading-relaxed font-medium mb-4">Irregular adherence pattern detected. AI suggests potential side effect interference.</p>
                  <button className="w-full py-2 bg-white border border-slate-200 text-slate-500 rounded-lg text-[10px] font-bold uppercase tracking-wider hover:bg-blue-600 hover:text-white hover:border-blue-600 transition-all flex items-center justify-center gap-2">
                    Agent Trace
                  </button>
                </div>
              </div>
            </div>

          </div>
        </div>
      </div>
    </div>
  );
}
