import { User, Shield, Key, Mail, Phone, MapPin, Award, History, Settings } from "lucide-react";

export default function PharmacistProfilePage() {
  return (
    <div className="h-full overflow-y-auto p-8">
      <div className="max-w-4xl mx-auto space-y-8">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-6">
            <div className="w-24 h-24 rounded-full bg-slate-900 border-4 border-white shadow-xl flex items-center justify-center text-white text-3xl font-bold">
              PP
            </div>
            <div>
              <h2 className="text-3xl font-bold text-slate-900 tracking-tight">Dr. Elizabeth Thorne</h2>
              <p className="text-lg text-slate-500 font-medium">Senior Clinical Pharmacist • ID: PH-99281</p>
              <div className="flex gap-4 mt-2">
                <span className="flex items-center gap-1.5 text-xs font-bold text-slate-400 uppercase tracking-widest"><Mail size={14} /> e.thorne@pharmaide.com</span>
                <span className="flex items-center gap-1.5 text-xs font-bold text-slate-400 uppercase tracking-widest"><Phone size={14} /> +1 (555) 012-3344</span>
              </div>
            </div>
          </div>
          <button className="px-6 py-2.5 bg-white border border-slate-200 text-slate-700 rounded-xl font-bold hover:bg-slate-50 transition-all shadow-sm flex items-center gap-2 cursor-pointer">
            <Settings size={18} />
            Account Settings
          </button>
        </div>

        <div className="grid grid-cols-3 gap-6">
          <div className="col-span-2 space-y-6">
            <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
              <h3 className="text-sm font-bold text-slate-400 uppercase tracking-widest mb-4 flex items-center gap-2">
                <Award size={16} /> Professional Credentials
              </h3>
              <div className="grid grid-cols-2 gap-6">
                <div>
                  <p className="text-xs font-bold text-slate-400 uppercase mb-1">Licensure</p>
                  <p className="text-sm font-bold text-slate-900">Registered Pharmacist (RPh)</p>
                  <p className="text-xs text-slate-500">Board of Pharmacy • Exp: Oct 2025</p>
                </div>
                <div>
                  <p className="text-xs font-bold text-slate-400 uppercase mb-1">Specialization</p>
                  <p className="text-sm font-bold text-slate-900">Cardiovascular Pharmacotherapy</p>
                  <p className="text-xs text-slate-500">BPS Certified</p>
                </div>
                <div>
                  <p className="text-xs font-bold text-slate-400 uppercase mb-1">Affiliation</p>
                  <p className="text-sm font-bold text-slate-900">St. Jude Medical Center</p>
                </div>
                <div>
                  <p className="text-xs font-bold text-slate-400 uppercase mb-1">Languages</p>
                  <p className="text-sm font-bold text-slate-900">English, Spanish</p>
                </div>
              </div>
            </div>

            <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
              <h3 className="text-sm font-bold text-slate-400 uppercase tracking-widest mb-4 flex items-center gap-2">
                <History size={16} /> Recent Activity
              </h3>
              <div className="space-y-4">
                {[
                  { action: "Resolved Escalation", details: "Adverse event flagged for P-7219 (Lisinopril)", time: "2h ago" },
                  { action: "Updated Protocol", details: "Modified 'Neuro-04' safety guard thresholds", time: "5h ago" },
                  { action: "Session Login", details: "Secure terminal access from 192.168.1.45", time: "8h ago" }
                ].map((act, i) => (
                  <div key={i} className="flex justify-between items-center p-3 hover:bg-slate-50 rounded-xl transition-colors">
                    <div>
                      <p className="text-sm font-bold text-slate-900">{act.action}</p>
                      <p className="text-xs text-slate-500">{act.details}</p>
                    </div>
                    <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">{act.time}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="space-y-6">
            <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
              <h3 className="text-sm font-bold text-slate-400 uppercase tracking-widest mb-4 flex items-center gap-2">
                <Shield size={16} /> System Access
              </h3>
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-slate-600 font-medium">Clinical Override</span>
                  <span className="px-2 py-0.5 bg-emerald-100 text-emerald-700 text-[10px] font-bold rounded uppercase">Active</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-slate-600 font-medium">Audit Logs View</span>
                  <span className="px-2 py-0.5 bg-emerald-100 text-emerald-700 text-[10px] font-bold rounded uppercase">Granted</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-slate-600 font-medium">PII Access</span>
                  <span className="px-2 py-0.5 bg-amber-100 text-amber-700 text-[10px] font-bold rounded uppercase">Restricted</span>
                </div>
                <div className="pt-4 border-t border-slate-100 mt-2">
                  <button className="w-full py-2 bg-slate-50 text-slate-400 rounded-lg text-xs font-bold uppercase tracking-widest hover:bg-slate-100 transition-all cursor-pointer">
                    Request Elevation
                  </button>
                </div>
              </div>
            </div>

            <div className="bg-slate-900 rounded-2xl p-6 shadow-lg shadow-slate-200 text-white">
              <div className="flex items-center gap-2 mb-4">
                <Key size={18} className="text-blue-400" />
                <h3 className="font-bold">Security Status</h3>
              </div>
              <p className="text-xs text-slate-400 leading-relaxed mb-4">
                Your session is protected by multi-factor authentication and clinical-grade encryption.
              </p>
              <div className="flex flex-col gap-2">
                <div className="flex justify-between text-[10px] font-bold uppercase tracking-widest">
                  <span>Session TTL</span>
                  <span>04:42:12</span>
                </div>
                <div className="w-full h-1 bg-slate-800 rounded-full overflow-hidden">
                  <div className="w-3/4 h-full bg-blue-500" />
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
