import {
  ArrowRight,
  ClipboardCheck,
  LockKeyhole,
  MessageCircle,
  Pill,
  Search,
  ShieldCheck,
  PlayCircle,
  Activity,
  AlertTriangle,
  FileText
} from "lucide-react";
import { useNavigate } from "react-router-dom";

export default function LandingPage() {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-slate-50 font-sans text-slate-900">
      <header className="sticky top-0 z-50 flex items-center justify-between px-8 py-4 bg-white/90 backdrop-blur-md border-b border-slate-200">
        <div className="flex items-center gap-12">
          <div className="flex items-center gap-3 text-blue-600 font-bold text-2xl tracking-tight">
            <span className="w-10 h-10 rounded-full bg-blue-600 text-white flex items-center justify-center">
              <Pill size={20} strokeWidth={2.2} />
            </span>
            <span>PharmaAide</span>
          </div>
          <nav className="hidden md:flex gap-8 font-medium text-slate-600">
            <a href="#platform" className="hover:text-blue-600 transition-colors">Platform</a>
            <a href="#workflow" className="hover:text-blue-600 transition-colors">Workflow</a>
            <a href="#demo" className="hover:text-blue-600 transition-colors">Intelligence</a>
            <a href="#safety" className="hover:text-blue-600 transition-colors">Security</a>
          </nav>
        </div>
        <div className="flex items-center gap-4">
          <button className="px-5 py-2.5 border border-slate-200 rounded-xl font-bold hover:bg-slate-50 transition-colors">
            Sign in
          </button>
          <button 
            className="px-5 py-2.5 bg-blue-600 text-white rounded-xl font-bold hover:bg-blue-700 transition-colors shadow-sm shadow-blue-200 flex items-center gap-2"
            onClick={() => navigate('/dashboard/triage')}
          >
            Enter Dashboard <ArrowRight size={16} />
          </button>
        </div>
      </header>

      <main>
        {/* Hero Section */}
        <section className="max-w-7xl mx-auto px-8 py-24 grid md:grid-cols-2 gap-16 items-center" id="platform">
          <div>
            <span className="inline-block px-3 py-1 mb-6 text-xs font-bold tracking-wider text-yellow-600 uppercase bg-yellow-50 border border-yellow-200 rounded-full">
              Clinical-Grade AI
            </span>
            <h1 className="text-5xl md:text-6xl font-bold leading-tight tracking-tight mb-6">
              The AI Pharmacist <br />
              <span className="text-blue-600">Always on Duty.</span>
            </h1>
            <p className="text-lg text-slate-600 mb-8 max-w-lg leading-relaxed">
              PharmaAide bridges the gap between clinical prescriptions and patient home-life via intelligent WhatsApp orchestration, keeping human pharmacists in complete control.
            </p>
            <div className="flex gap-4">
              <button 
                className="px-6 py-3 bg-blue-600 text-white rounded-xl font-bold hover:bg-blue-700 transition-all shadow-md shadow-blue-200 flex items-center gap-2"
                onClick={() => navigate('/dashboard/triage')}
              >
                Launch Platform
              </button>
              <button className="px-6 py-3 bg-white border border-slate-200 text-slate-800 rounded-xl font-bold hover:bg-slate-50 transition-all flex items-center gap-2">
                <PlayCircle size={18} />
                Watch Demo
              </button>
            </div>
          </div>
          <div className="bg-white rounded-3xl border border-slate-200 shadow-xl shadow-slate-200/50 h-[480px] relative overflow-hidden flex items-center justify-center p-8">
            <div className="absolute inset-0 opacity-[0.03]" style={{ backgroundImage: 'radial-gradient(#000 2px, transparent 2px)', backgroundSize: '24px 24px' }}></div>
            <div className="relative z-10 bg-white border border-slate-200 rounded-2xl p-6 shadow-2xl flex items-center gap-6 w-full max-w-md">
              <div className="w-16 h-16 bg-blue-50 text-blue-600 rounded-full flex items-center justify-center shrink-0">
                <ShieldCheck size={32} />
              </div>
              <div>
                <h3 className="font-bold text-lg">System Active</h3>
                <p className="text-sm text-slate-500">Monitoring 2,401 active treatments across 4 facilities.</p>
              </div>
            </div>
          </div>
        </section>

        {/* Workflow */}
        <section className="bg-white border-y border-slate-200 py-24" id="workflow">
          <div className="max-w-7xl mx-auto px-8">
            <div className="text-center mb-16">
              <h2 className="text-4xl font-bold mb-4 tracking-tight">The Human-in-the-Loop Workflow</h2>
              <p className="text-lg text-slate-600 max-w-2xl mx-auto">Automated engagement with mandatory pharmacist oversight for clinical decisions.</p>
            </div>
            
            <div className="grid md:grid-cols-3 gap-8">
              <div className="bg-slate-50 border border-slate-200 rounded-3xl p-8 hover:-translate-y-1 transition-transform relative">
                <div className="w-14 h-14 bg-white border border-slate-200 text-slate-800 rounded-2xl flex items-center justify-center mb-6 shadow-sm">
                  <FileText size={28} />
                </div>
                <h3 className="text-xl font-bold mb-3">1. Pharmacist Setup</h3>
                <p className="text-slate-600 leading-relaxed">Set clinical objectives, verify prescriptions, and define parameters within the secure dashboard.</p>
              </div>
              
              <div className="bg-blue-600 text-white rounded-3xl p-8 hover:-translate-y-1 transition-transform shadow-lg shadow-blue-200 relative">
                <div className="w-14 h-14 bg-white text-blue-600 rounded-2xl flex items-center justify-center mb-6 shadow-sm">
                  <MessageCircle size={28} />
                </div>
                <h3 className="text-xl font-bold mb-3">2. PAAS Agent</h3>
                <p className="text-blue-100 leading-relaxed">Engages patients naturally via WhatsApp, utilizing clinical reasoning to track adherence.</p>
              </div>

              <div className="bg-slate-50 border border-slate-200 rounded-3xl p-8 hover:-translate-y-1 transition-transform relative">
                <div className="w-14 h-14 bg-white border border-slate-200 text-slate-800 rounded-2xl flex items-center justify-center mb-6 shadow-sm">
                  <Activity size={28} />
                </div>
                <h3 className="text-xl font-bold mb-3">3. Clinical Command</h3>
                <p className="text-slate-600 leading-relaxed">Real-time triage queue, severity-based flagging, and comprehensive oversight.</p>
              </div>
            </div>
          </div>
        </section>

        {/* Demo */}
        <section className="max-w-7xl mx-auto px-8 py-24" id="demo">
          <div className="grid md:grid-cols-2 gap-16 items-center">
            <div>
              <h2 className="text-4xl font-bold mb-6 tracking-tight">See the Agent Think</h2>
              <p className="text-lg text-slate-600 mb-8 leading-relaxed">Experience how our PAAS agent analyzes patient responses, identifies potential side effects, and maps them to clinical guidelines in real-time.</p>
              <button className="px-5 py-2.5 bg-yellow-400 text-yellow-950 rounded-xl font-bold hover:bg-yellow-500 transition-colors shadow-sm flex items-center gap-2">
                <PlayCircle size={18} />
                Play Interactive Demo
              </button>
            </div>
            <div className="bg-slate-100 border border-slate-200 border-dashed rounded-3xl p-8 flex items-center justify-center min-h-[400px]">
              <div className="bg-white border border-slate-200 rounded-2xl p-6 w-full max-w-md shadow-xl shadow-slate-200/50">
                <div className="flex items-center gap-4 mb-6 pb-4 border-b border-slate-100">
                  <div className="w-10 h-10 rounded-full bg-slate-100 flex items-center justify-center font-bold text-slate-700">PT</div>
                  <div>
                    <h4 className="font-bold text-sm">Patient (WhatsApp)</h4>
                    <p className="text-sm text-slate-600">"I stopped taking the lisinopril, it gave me a cough."</p>
                  </div>
                </div>
                <div className="space-y-3">
                  <div className="flex items-center gap-3 p-3 rounded-xl bg-slate-50 border border-slate-100 text-sm font-medium text-slate-700">
                    <Search size={16} className="text-blue-500" /> Analyzing intent: Side effect reported
                  </div>
                  <div className="flex items-center gap-3 p-3 rounded-xl bg-slate-50 border border-slate-100 text-sm font-medium text-slate-700">
                    <ClipboardCheck size={16} className="text-blue-500" /> Cross-referencing RxNorm
                  </div>
                  <div className="flex items-center gap-3 p-3 rounded-xl bg-red-50 border border-red-100 text-sm font-medium text-red-700">
                    <AlertTriangle size={16} /> Flag for Pharmacist Review
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

      </main>

      <footer className="bg-white border-t border-slate-200 py-12 px-8">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div className="flex gap-6 text-sm font-medium text-slate-500">
            <a href="#" className="hover:text-slate-900">Privacy</a>
            <a href="#" className="hover:text-slate-900">Terms</a>
            <a href="#" className="hover:text-slate-900">HIPAA</a>
          </div>
          <div className="text-sm text-slate-500 bg-slate-100 px-4 py-1.5 rounded-full">
            &copy; 2026 PharmaAide
          </div>
        </div>
      </footer>
    </div>
  );
}
