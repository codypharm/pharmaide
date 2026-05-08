import { Filter, Search, ChevronDown, Download } from "lucide-react";
import { useOutletContext } from "react-router-dom";

type OutletContext = {
  isPrivacyMode: boolean;
};

const MOCK_PATIENTS = [
  { id: "P-4492", name: "Jameson, M.", riskLevel: "High", adherence: 62, lastInteraction: "10m ago", protocol: "Cardio-01" },
  { id: "P-8821", name: "Chen, L.", riskLevel: "Elevated", adherence: 78, lastInteraction: "2h ago", protocol: "Endo-04" },
  { id: "P-1102", name: "Smith, A.", riskLevel: "Stable", adherence: 95, lastInteraction: "1d ago", protocol: "Resp-02" },
  { id: "P-3345", name: "Garcia, R.", riskLevel: "Elevated", adherence: 81, lastInteraction: "3h ago", protocol: "Cardio-01" },
  { id: "P-9910", name: "Okafor, E.", riskLevel: "Stable", adherence: 98, lastInteraction: "5h ago", protocol: "Neuro-01" },
];

export default function PatientSurveillancePage() {
  const { isPrivacyMode } = useOutletContext<OutletContext>();

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-slate-900 mb-1">Patient Surveillance</h2>
          <p className="text-sm text-slate-500">Active monitoring directory with real-time adherence scoring.</p>
        </div>
        <div className="flex gap-3">
          <button className="px-4 py-2 bg-white border border-slate-200 text-slate-700 rounded-xl font-semibold hover:bg-slate-50 transition-colors shadow-sm flex items-center gap-2">
            <Filter size={16} />
            Filters
          </button>
          <button className="px-4 py-2 bg-blue-600 text-white rounded-xl font-semibold hover:bg-blue-700 transition-colors shadow-sm shadow-blue-200 flex items-center gap-2">
            <Download size={16} />
            Export Data
          </button>
        </div>
      </div>

      <div className="bg-white border border-slate-200 rounded-2xl shadow-sm shadow-slate-100/50 overflow-hidden flex flex-col">
        <div className="p-4 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
          <div className="relative w-72">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input 
              placeholder="Search patients by ID or name..." 
              className="w-full pl-9 pr-4 py-1.5 bg-white border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-100 focus:border-blue-500"
            />
          </div>
          <div className="flex gap-2">
            <button className="px-3 py-1.5 text-sm font-medium text-slate-600 border border-slate-200 bg-white rounded-lg hover:bg-slate-50 flex items-center gap-2">
              Risk Level <ChevronDown size={14} />
            </button>
            <button className="px-3 py-1.5 text-sm font-medium text-slate-600 border border-slate-200 bg-white rounded-lg hover:bg-slate-50 flex items-center gap-2">
              Protocol <ChevronDown size={14} />
            </button>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-slate-50/50 border-b border-slate-200">
                <th className="px-6 py-4 text-[11px] font-bold tracking-wider text-slate-500 uppercase">Patient Directory</th>
                <th className="px-6 py-4 text-[11px] font-bold tracking-wider text-slate-500 uppercase">Last Interaction</th>
                <th className="px-6 py-4 text-[11px] font-bold tracking-wider text-slate-500 uppercase">Active Protocol</th>
                <th className="px-6 py-4 text-[11px] font-bold tracking-wider text-slate-500 uppercase">Clinical Risk</th>
                <th className="px-6 py-4 text-[11px] font-bold tracking-wider text-slate-500 uppercase">Adherence Score</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {MOCK_PATIENTS.map((patient) => (
                <tr key={patient.id} className="hover:bg-slate-50/80 transition-colors group">
                  <td className="px-6 py-4">
                    <div className="flex flex-col gap-1">
                      <span className="font-mono text-sm font-bold text-slate-900">{patient.id}</span>
                      <span className={`text-sm ${isPrivacyMode ? "blur-sm hover:blur-none transition-all duration-300 cursor-pointer bg-slate-200 text-transparent hover:bg-transparent hover:text-slate-600 rounded px-1 inline-block w-fit" : "text-slate-600"}`}>
                        {patient.name}
                      </span>
                    </div>
                  </td>
                  <td className="px-6 py-4 text-sm text-slate-600 font-medium">{patient.lastInteraction}</td>
                  <td className="px-6 py-4 text-sm text-slate-600 font-medium">{patient.protocol}</td>
                  <td className="px-6 py-4">
                    <span className={`px-2.5 py-1 rounded-md text-[10px] font-bold tracking-wider uppercase inline-block ${
                      patient.riskLevel === 'High' ? 'bg-red-100 text-red-700' : 
                      patient.riskLevel === 'Elevated' ? 'bg-yellow-100 text-yellow-700' : 
                      'bg-emerald-100 text-emerald-700'
                    }`}>
                      {patient.riskLevel}
                    </span>
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-3">
                      <div className="flex-1 h-2 bg-slate-100 rounded-full overflow-hidden max-w-[120px]">
                        <div 
                          className={`h-full rounded-full ${
                            patient.adherence < 70 ? 'bg-red-500' : 
                            patient.adherence < 85 ? 'bg-yellow-500' : 'bg-emerald-500'
                          }`}
                          style={{ width: `${patient.adherence}%` }}
                        />
                      </div>
                      <span className="text-sm font-bold text-slate-700 w-8">{patient.adherence}%</span>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        
        <div className="p-4 border-t border-slate-100 bg-slate-50/50 flex items-center justify-between text-sm text-slate-500">
          <span>Showing 1-5 of 2,401 patients</span>
          <div className="flex gap-1">
            <button className="px-3 py-1 border border-slate-200 bg-white rounded-md hover:bg-slate-50 disabled:opacity-50" disabled>Prev</button>
            <button className="px-3 py-1 border border-slate-200 bg-white rounded-md hover:bg-slate-50">Next</button>
          </div>
        </div>
      </div>
    </div>
  );
}
