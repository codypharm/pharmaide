import { ChevronDown, Calendar } from "lucide-react";
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
  const days = Array.from({ length: 30 }, (_, i) => 30 - i); // 30 down to 1

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-slate-900 mb-1">Adherence Heatmaps</h2>
          <p className="text-sm text-slate-500">30-day longitudinal view of patient medication adherence patterns.</p>
        </div>
        <div className="flex gap-3">
          <button className="px-4 py-2 bg-white border border-slate-200 text-slate-700 rounded-xl font-semibold hover:bg-slate-50 transition-colors shadow-sm flex items-center gap-2">
            <Calendar size={16} />
            Last 30 Days <ChevronDown size={14} />
          </button>
        </div>
      </div>

      <div className="flex gap-6 items-start">
        <div className="flex-1 bg-white border border-slate-200 rounded-2xl shadow-sm shadow-slate-100/50 overflow-hidden flex flex-col">
          <div className="p-4 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
            <div className="flex gap-4">
              <div className="flex flex-col gap-1">
                <label className="text-[10px] font-bold tracking-wider text-slate-400 uppercase">Protocol</label>
                <select className="bg-white border border-slate-200 rounded-md px-3 py-1.5 text-sm outline-none w-40">
                  <option>All Protocols</option>
                  <option>Cardio-01</option>
                  <option>Neuro-04</option>
                </select>
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-[10px] font-bold tracking-wider text-slate-400 uppercase">Sort By</label>
                <select className="bg-white border border-slate-200 rounded-md px-3 py-1.5 text-sm outline-none w-40">
                  <option>Risk (Highest First)</option>
                  <option>Adherence (Lowest First)</option>
                  <option>Patient ID</option>
                </select>
              </div>
            </div>

            <div className="flex items-center gap-4 bg-white border border-slate-200 rounded-lg px-4 py-2 shadow-sm">
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-sm bg-blue-600"></div>
                <span className="text-[11px] font-bold tracking-wider text-slate-500 uppercase">Taken</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-sm bg-red-500"></div>
                <span className="text-[11px] font-bold tracking-wider text-slate-500 uppercase">Missed</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-sm bg-slate-100"></div>
                <span className="text-[11px] font-bold tracking-wider text-slate-500 uppercase">No Data</span>
              </div>
            </div>
          </div>

          <div className="overflow-x-auto p-6">
            <div className="min-w-max">
              {/* Timeline Header */}
              <div className="flex items-center mb-4 pl-36">
                {days.map(day => (
                  <div key={day} className="w-4 mx-0.5 text-center text-[9px] font-bold text-slate-400">
                    {day % 5 === 0 || day === 1 ? day : ''}
                  </div>
                ))}
              </div>

              {/* Matrix Rows */}
              <div className="flex flex-col gap-2">
                {MOCK_HEATMAP_DATA.map((pt) => (
                  <div key={pt.id} className="flex items-center group">
                    <div className="w-36 shrink-0 pr-4 flex flex-col gap-0.5">
                      <span className={`font-mono text-sm font-bold ${pt.isCritical ? 'text-red-600' : 'text-slate-900'}`}>
                        {pt.id}
                      </span>
                    </div>
                    <div className="flex bg-slate-50 p-1 rounded-lg border border-slate-100">
                      {pt.history.map((status, i) => (
                        <div 
                          key={i} 
                          className={`w-4 h-6 mx-0.5 rounded-sm hover:opacity-80 transition-opacity cursor-crosshair ${
                            status === 'taken' ? 'bg-blue-600' :
                            status === 'missed' ? 'bg-red-500' : 'bg-slate-200'
                          }`}
                          title={`Day ${30-i}: ${status}`}
                        />
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Critical Alerts Sidebar */}
        <div className="w-80 shrink-0 flex flex-col gap-4">
          <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm">
            <div className="flex items-center gap-2 text-slate-900 mb-4 border-b border-slate-100 pb-3">
              <h3 className="font-bold">Intervention Required</h3>
            </div>
            
            <div className="flex flex-col gap-3">
              <div className="bg-white rounded-xl p-3 shadow-sm border border-slate-100">
                <div className="flex justify-between items-start mb-2">
                  <span className="font-mono text-sm font-bold text-slate-900">P-4492</span>
                  <span className="bg-red-100 text-red-700 px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider">3 Missed</span>
                </div>
                <p className="text-xs text-slate-600 leading-relaxed">Consecutive missed doses of Apixaban reported.</p>
              </div>

              <div className="bg-white rounded-xl p-3 shadow-sm border border-slate-100">
                <div className="flex justify-between items-start mb-2">
                  <span className="font-mono text-sm font-bold text-slate-900">P-7734</span>
                  <span className="bg-red-100 text-red-700 px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider">7 Missed</span>
                </div>
                <p className="text-xs text-slate-600 leading-relaxed">Irregular adherence pattern detected over last 14 days.</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
