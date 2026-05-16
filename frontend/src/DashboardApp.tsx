import { Activity, Bell, ClipboardList, FileText, Flame, Map, Search, ShieldCheck, Plus, ChevronRight } from "lucide-react";
import { useState } from "react";
import { Outlet, NavLink, Link } from "react-router-dom";

function DashboardApp() {
  const [isPrivacyMode, setIsPrivacyMode] = useState(false);

  return (
    <div className="flex h-screen overflow-hidden bg-slate-50 font-sans text-slate-900">
      {/* Sidebar */}
      <aside className="w-64 bg-white border-r border-slate-200 flex flex-col z-40">
        <div className="p-8 pb-4">
          <Link to="/" className="flex items-center gap-2 group cursor-pointer">
            <div className="w-9 h-9 bg-[#5548E8] rounded-xl flex items-center justify-center text-white shadow-sm group-hover:bg-[#463AD4] transition-colors">
              <ShieldCheck size={20} />
            </div>
            <h1 className="text-xl font-bold tracking-tighter text-slate-900 group-hover:text-[#5548E8] transition-colors">PharmaAide</h1>
          </Link>
        </div>

        <nav className="flex flex-col gap-0.5 px-3 flex-1 mt-6">
          <NavLink
            to="/dashboard/triage"
            className={({ isActive }) => 
              `flex items-center gap-3 px-4 py-2.5 rounded-xl text-sm font-medium transition-all ${
                isActive 
                  ? "bg-slate-100 text-slate-900" 
                  : "text-slate-500 hover:bg-slate-50 hover:text-slate-900"
              }`
            }
          >
            <Flame size={18} />
            Triage Queue
          </NavLink>
          <NavLink
            to="/dashboard/surveillance"
            className={({ isActive }) =>
              `flex items-center gap-3 px-4 py-2.5 rounded-xl text-sm font-medium transition-all ${
                isActive
                  ? "bg-slate-100 text-slate-900"
                  : "text-slate-500 hover:bg-slate-50 hover:text-slate-900"
              }`
            }
          >
            <Activity size={18} />
            Surveillance
          </NavLink>
          <NavLink
            to="/dashboard/ingestions"
            className={({ isActive }) =>
              `flex items-center gap-3 px-4 py-2.5 rounded-xl text-sm font-medium transition-all ${
                isActive
                  ? "bg-slate-100 text-slate-900"
                  : "text-slate-500 hover:bg-slate-50 hover:text-slate-900"
              }`
            }
          >
            <ClipboardList size={18} />
            Treatments
          </NavLink>
          <NavLink
            to="/dashboard/heatmaps"
            className={({ isActive }) => 
              `flex items-center gap-3 px-4 py-2.5 rounded-xl text-sm font-medium transition-all ${
                isActive 
                  ? "bg-slate-100 text-slate-900" 
                  : "text-slate-500 hover:bg-slate-50 hover:text-slate-900"
              }`
            }
          >
            <Map size={18} />
            Adherence
          </NavLink>
          
          <div className="h-px bg-slate-100 my-4 mx-4" />

          <NavLink
            to="/dashboard/knowledge"
            className={({ isActive }) => 
              `flex items-center gap-3 px-4 py-2.5 rounded-xl text-sm font-medium transition-all ${
                isActive 
                  ? "bg-slate-100 text-slate-900" 
                  : "text-slate-500 hover:bg-slate-50 hover:text-slate-900"
              }`
            }
          >
            <FileText size={18} />
            Clinical Assets
          </NavLink>
          <NavLink
            to="/dashboard/audits"
            className={({ isActive }) => 
              `flex items-center gap-3 px-4 py-2.5 rounded-xl text-sm font-medium transition-all ${
                isActive 
                  ? "bg-slate-100 text-slate-900" 
                  : "text-slate-500 hover:bg-slate-50 hover:text-slate-900"
              }`
            }
          >
            <ShieldCheck size={18} />
            System Audit
          </NavLink>

          <div className="mt-8 px-4">
            <Link 
              to="/dashboard/new-treatment"
              className="w-full bg-[#5548E8] hover:bg-[#463AD4] !text-white py-2.5 rounded-xl flex items-center justify-center gap-2 text-sm font-bold transition-all shadow-sm shadow-[#D9D5FB]"
            >
              <Plus size={18} />
              New Treatment
            </Link>
          </div>
        </nav>

        <Link to="/dashboard/profile" className="p-4 m-4 bg-slate-50 rounded-2xl flex items-center gap-3 hover:bg-slate-100 transition-all cursor-pointer border border-slate-100">
          <div className="w-10 h-10 rounded-xl bg-white border border-slate-200 flex items-center justify-center font-bold text-slate-700 shadow-sm">PP</div>
          <div className="flex-1 min-w-0">
            <p className="text-xs font-bold text-slate-900 truncate">Dr. E. Thorne</p>
            <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Pharmacist</p>
          </div>
          <ChevronRight size={14} className="text-slate-300" />
        </Link>
      </aside>

      {/* Workspace */}
      <main className="flex-1 flex flex-col min-w-0 bg-slate-50/50">
        <header className="h-16 bg-white border-b border-slate-200 flex items-center justify-between px-8 z-30 shadow-sm shadow-slate-100/50">
          <div className="relative w-80">
            <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input 
              placeholder="Search Directory..." 
              type="text" 
              className="w-full pl-10 pr-4 py-2 bg-slate-50 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-[#D9D5FB] focus:border-[#5548E8] transition-all"
            />
          </div>

          <div className="flex items-center gap-6">
            <label className="flex items-center gap-3 cursor-pointer group">
              <span className="text-sm font-semibold text-slate-600 group-hover:text-slate-900 transition-colors">Privacy Mode</span>
              <div className="relative inline-flex items-center cursor-pointer">
                <input 
                  type="checkbox" 
                  value="" 
                  className="sr-only peer" 
                  checked={isPrivacyMode}
                  onChange={(e) => setIsPrivacyMode(e.target.checked)}
                />
                <div className="w-11 h-6 bg-slate-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full rtl:peer-checked:after:-translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:start-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-[#5548E8]"></div>
              </div>
            </label>
            <button className="w-10 h-10 rounded-full hover:bg-slate-100 text-slate-500 flex items-center justify-center relative transition-colors">
              <Bell size={20} />
              <span className="absolute top-2.5 right-2.5 w-2 h-2 bg-red-500 rounded-full border-2 border-white"></span>
            </button>
            <div className="pl-6 border-l border-slate-200 flex items-center gap-3">
              <span className="text-sm font-semibold text-slate-700">Thomas F.</span>
              <div className="w-8 h-8 bg-yellow-100 text-yellow-800 rounded-full flex items-center justify-center font-bold text-xs">TF</div>
            </div>
          </div>
        </header>

        <div className="flex-1 overflow-hidden">
          <Outlet context={{ isPrivacyMode }} />
        </div>
      </main>
    </div>
  );
}

export default DashboardApp;
