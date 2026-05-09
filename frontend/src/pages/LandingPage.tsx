import { 
  ArrowRight, 
  Pill, 
  ShieldCheck, 
  Zap, 
  Users, 
  Lock, 
  Globe, 
  CheckCircle2, 
  PlayCircle,
  MessageSquare,
  Activity,
  Search,
  ChevronRight,
  Shield,
  Bot,
  Layers
} from "lucide-react";
import { useNavigate } from "react-router-dom";

export default function LandingPage() {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-[#F5F5F6] font-['Public_Sans'] text-slate-900 overflow-x-hidden selection:bg-blue-100 selection:text-blue-900">
      {/* Background Mesh Gradient */}
      <div className="fixed inset-0 -z-10 overflow-hidden pointer-events-none">
        <div className="absolute top-[-20%] left-[-10%] w-[60%] h-[60%] bg-blue-100/30 rounded-full blur-[120px]" />
        <div className="absolute bottom-[-10%] right-[-5%] w-[50%] h-[50%] bg-teal-100/20 rounded-full blur-[100px]" />
        <div className="absolute top-[30%] left-[40%] w-[40%] h-[40%] bg-slate-200/20 rounded-full blur-[140px]" />
      </div>

      {/* Top Navbar */}
      <nav className="fixed top-0 left-0 right-0 z-[100] px-8 py-5 bg-white/60 backdrop-blur-2xl border-b border-slate-100/50 flex items-center justify-between">
        <div className="flex items-center gap-16">
          <div className="flex items-center gap-2.5 group cursor-pointer" onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}>
            <div className="w-10 h-10 bg-blue-600 rounded-xl flex items-center justify-center text-white shadow-xl shadow-blue-600/10 group-hover:scale-105 transition-transform duration-500">
              <Shield size={22} strokeWidth={2.5} />
            </div>
            <span className="text-xl font-extrabold tracking-tighter text-slate-900">PharmaAide</span>
          </div>
          <div className="hidden lg:flex items-center gap-10">
            {["Solutions", "Safety", "Security", "Clinical Intelligence"].map((item) => (
              <a 
                key={item} 
                href={`#${item.toLowerCase().replace(' ', '-')}`} 
                className="text-[13px] font-bold text-slate-500 hover:text-slate-900 transition-all hover:translate-y-[-1px]"
              >
                {item}
              </a>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-4">
          <button 
            onClick={() => navigate('/dashboard/surveillance')}
            className="px-6 py-2.5 text-[13px] font-bold text-slate-500 hover:text-slate-900 transition-colors cursor-pointer"
          >
            Clinical Login
          </button>
          <button 
            onClick={() => navigate('/dashboard/triage')}
            className="px-6 py-2.5 bg-blue-600 text-white rounded-xl text-[13px] font-bold hover:bg-blue-700 transition-all cursor-pointer"
          >
            Launch Command Center
          </button>
        </div>
      </nav>

      {/* Hero Section */}
      <header className="relative pt-48 pb-32 px-8 max-w-7xl mx-auto">
        <div className="grid lg:grid-cols-2 gap-24 items-center">
          <div className="relative z-10">
            
            <h1 className="text-7xl lg:text-8xl font-black leading-[0.9] tracking-tighter mb-10 text-slate-900">
              The <span className="text-transparent bg-clip-text bg-gradient-to-r from-teal-600 to-blue-600">Intelligence</span> <br />
              Layer for <br />
              Patient Care.
            </h1>
            <p className="text-xl text-slate-500 leading-relaxed mb-12 max-w-lg font-medium">
              Bridging the clinical gap with agentic AI grounded in precision. Automate adherence, triage side effects, and empower pharmacists.
            </p>
            <div className="flex items-center gap-4">
              <button 
                onClick={() => navigate('/dashboard/triage')}
                className="px-8 py-4 bg-blue-600 text-white rounded-xl font-bold hover:bg-blue-700 transition-all flex items-center gap-2 active:scale-95 cursor-pointer"
              >
                Get Started
                <ArrowRight size={18} />
              </button>
              <button className="px-8 py-4 bg-white border border-slate-200 text-slate-900 rounded-xl font-bold hover:bg-slate-50 transition-all active:scale-95 cursor-pointer">
                View Documentation
              </button>
            </div>
            
            <div className="mt-20 flex items-center gap-12 grayscale opacity-40">
              <div className="font-black text-2xl tracking-tighter">DailyMed</div>
              <div className="font-black text-2xl tracking-tighter">RxNorm</div>
              <div className="font-black text-2xl tracking-tighter">HL7 FHIR</div>
            </div>
          </div>
          
          <div className="relative lg:h-[700px] flex items-center justify-center">
            {/* Visual Abstract UI Element */}
            <div className="relative w-full max-w-md aspect-[4/5] bg-white rounded-[40px] shadow-[0_50px_100px_-20px_rgba(0,0,0,0.15)] border border-slate-100 p-8 flex flex-col gap-6 overflow-hidden rotate-2 hover:rotate-0 transition-transform duration-700 group">
              <div className="flex items-center justify-between border-b border-slate-50 pb-6">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 bg-teal-50 text-teal-600 rounded-xl flex items-center justify-center">
                    <ShieldCheck size={20} />
                  </div>
                  <div>
                    <div className="text-[11px] font-bold text-slate-400 uppercase tracking-widest">System Status</div>
                    <div className="text-sm font-bold text-slate-900">Clinically Grounded</div>
                  </div>
                </div>
                <div className="w-2 h-2 bg-emerald-500 rounded-full animate-ping" />
              </div>
              
              <div className="space-y-4 py-4">
                <div className="h-4 w-3/4 bg-slate-50 rounded-full" />
                <div className="h-4 w-1/2 bg-slate-50 rounded-full" />
                <div className="h-24 w-full bg-slate-50/50 rounded-3xl border border-dashed border-slate-200 flex items-center justify-center text-slate-300">
                  <Bot size={32} />
                </div>
              </div>
              
              <div className="mt-auto pt-6 border-t border-slate-50 flex items-center gap-4">
                <div className="w-8 h-8 rounded-full bg-slate-100" />
                <div className="flex-1 space-y-2">
                  <div className="h-2 w-1/2 bg-slate-100 rounded-full" />
                  <div className="h-2 w-1/3 bg-slate-50 rounded-full" />
                </div>
              </div>
              
              {/* Floating Decorative Elements */}
              <div className="absolute -top-10 -right-10 w-32 h-32 bg-teal-500/10 rounded-full blur-2xl group-hover:bg-teal-500/20 transition-colors" />
            </div>
            
            {/* Background Circle Gradient */}
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,_var(--tw-gradient-stops))] from-teal-100/40 via-transparent to-transparent -z-10 scale-150" />
          </div>
        </div>
      </header>

      {/* Philosophy Section */}
      <section className="bg-[#131b2e] py-40 px-8 relative overflow-hidden" id="safety">
        <div className="absolute inset-0 bg-gradient-to-b from-transparent to-blue-900/10 opacity-30 pointer-events-none" />
        <div className="max-w-5xl mx-auto text-center relative z-10">
          <div className="inline-block px-5 py-1.5 bg-white/5 border border-white/10 rounded-full text-[10px] font-black text-blue-400 uppercase tracking-[0.3em] mb-12">
            Safety-First Architecture
          </div>
          <h2 className="text-5xl lg:text-7xl font-bold text-white mb-10 tracking-tighter leading-tight">
            AI with a <span className="italic text-blue-400">Clinical Soul.</span>
          </h2>
          <p className="text-xl lg:text-2xl text-slate-400 leading-relaxed font-medium max-w-3xl mx-auto">
            Traditional health-tech is passive. PharmaAide is <span className="text-white font-bold">agentic.</span> Our systems don't just remind—they reason, triage, and act as a digital twin for the pharmacist.
          </p>
        </div>
      </section>

      {/* Features Grid */}
      <section className="py-40 px-8 max-w-7xl mx-auto" id="solutions">
        <div className="flex flex-col lg:flex-row items-end justify-between mb-24 gap-8">
          <div className="max-w-2xl">
            <h2 className="text-5xl font-black text-slate-900 mb-6 tracking-tighter">Unified Adherence Operations</h2>
            <p className="text-xl text-slate-500 font-medium">Everything you need to manage patient adherence at scale, with the precision of a clinical team.</p>
          </div>
          <button className="px-8 py-4 bg-blue-50 border border-blue-100 text-blue-600 rounded-2xl font-bold flex items-center gap-2 hover:bg-blue-100 transition-all">
            Explore All Features
            <ChevronRight size={18} />
          </button>
        </div>

        <div className="grid lg:grid-cols-3 gap-8">
          {[
            { 
              icon: Search, 
              title: "Triage & Reasoning", 
              desc: "Automated analysis of patient chat history to surface side effects, non-compliance, and medication concerns before they escalate.",
              color: "bg-blue-50 text-blue-600"
            },
            { 
              icon: MessageSquare, 
              title: "WhatsApp Engagement", 
              desc: "Natural conversations powered by LLMs grounded in your specific clinical guidelines. No more rigid menu-based bots.",
              color: "bg-emerald-50 text-emerald-600"
            },
            { 
              icon: Shield, 
              title: "Clinical Guardrails", 
              desc: "Multi-layer safety checks ensuring all AI output is verified against drug databases and HIPAA-compliant standards.",
              color: "bg-teal-50 text-teal-600"
            }
          ].map((feature, i) => (
            <div key={i} className="group p-10 bg-white border border-slate-100 rounded-[32px] hover:shadow-[0_40px_80px_-20px_rgba(0,0,0,0.1)] transition-all duration-500 hover:-translate-y-2">
              <div className={`w-14 h-14 ${feature.color} rounded-2xl flex items-center justify-center mb-8 shadow-sm group-hover:scale-110 transition-transform`}>
                <feature.icon size={28} />
              </div>
              <h3 className="text-2xl font-bold mb-4 text-slate-900">{feature.title}</h3>
              <p className="text-slate-500 leading-relaxed font-medium">{feature.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Visual Demo Section */}
      <section className="bg-slate-50 py-40 px-8 overflow-hidden" id="clinical-intelligence">
        <div className="max-w-7xl mx-auto grid lg:grid-cols-2 gap-24 items-center">
          <div className="relative">
            <div className="absolute inset-0 bg-gradient-to-br from-teal-400/20 to-blue-400/20 blur-3xl opacity-30" />
            <div className="relative bg-[#131b2e] rounded-[40px] p-2 shadow-2xl overflow-hidden border border-white/10">
              <div className="bg-slate-800 rounded-[36px] overflow-hidden border border-white/5 aspect-video flex items-center justify-center">
                 <div className="flex flex-col items-center gap-4">
                    <PlayCircle size={64} className="text-teal-400 animate-pulse" />
                    <span className="text-white/50 font-bold uppercase tracking-widest text-[10px]">Interactive Session Preview</span>
                 </div>
              </div>
            </div>
          </div>
          <div>
            <div className="inline-flex items-center gap-2 px-3 py-1 bg-amber-50 border border-amber-100 rounded-full text-[10px] font-bold text-amber-600 uppercase tracking-wider mb-8">
              Live Reasoning Engine
            </div>
            <h2 className="text-5xl font-black text-slate-900 mb-8 tracking-tighter leading-tight">
              A Dashboard That <br />
              <span className="text-teal-600 italic">Thinks</span> With You.
            </h2>
            <p className="text-xl text-slate-500 leading-relaxed mb-10 font-medium">
              PharmaAide doesn't just show data; it provides clinical context. See exactly why an agent flagged a patient, with citations from RxNorm and treatment history.
            </p>
            <ul className="space-y-6 mb-12">
              {["Real-time triage scoring", "Side-effect causal mapping", "Automated intervention drafting"].map((item, i) => (
                <li key={i} className="flex items-center gap-3 text-slate-700 font-bold">
                  <div className="w-6 h-6 bg-emerald-50 text-emerald-600 rounded-full flex items-center justify-center shrink-0">
                    <CheckCircle2 size={14} />
                  </div>
                  {item}
                </li>
              ))}
            </ul>
            <button 
              onClick={() => navigate('/dashboard/triage')}
              className="px-10 py-5 bg-blue-600 text-white rounded-[24px] font-bold shadow-2xl shadow-blue-900/20 hover:bg-blue-700 transition-all active:scale-95 cursor-pointer"
            >
              Explore Command Center
            </button>
          </div>
        </div>
      </section>

      {/* CTA Footer */}
      <footer className="bg-white py-40 px-8 border-t border-slate-100">
        <div className="max-w-4xl mx-auto text-center">
          <div className="w-20 h-20 bg-blue-600 rounded-[28px] flex items-center justify-center text-white mx-auto mb-12 shadow-2xl shadow-blue-600/20">
            <Shield size={40} />
          </div>
          <h2 className="text-5xl lg:text-7xl font-black text-slate-900 mb-8 tracking-tighter">Ready to evolve?</h2>
          <p className="text-2xl text-slate-400 font-medium mb-16 leading-relaxed">
            Join the elite pharmacies leveraging agentic AI to redefine patient adherence and clinical safety.
          </p>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-6">
            <button 
              onClick={() => navigate('/dashboard/triage')}
              className="w-full sm:w-auto px-12 py-6 bg-blue-600 text-white rounded-[30px] font-bold shadow-2xl shadow-blue-900/30 hover:bg-blue-700 transition-all hover:scale-105 active:scale-95"
            >
              Get Started for Free
            </button>
            <button className="w-full sm:w-auto px-12 py-6 bg-white border border-slate-200 text-slate-900 rounded-[30px] font-bold hover:bg-slate-50 transition-all">
              Talk to a Specialist
            </button>
          </div>
          
          <div className="mt-32 pt-16 border-t border-slate-50 flex flex-col md:flex-row items-center justify-between gap-8 text-[11px] font-black text-slate-400 uppercase tracking-[0.2em]">
            <div className="flex items-center gap-8">
              <a href="#" className="hover:text-slate-900 transition-colors">Privacy</a>
              <a href="#" className="hover:text-slate-900 transition-colors">Security</a>
              <a href="#" className="hover:text-slate-900 transition-colors">Terms</a>
            </div>
            <div>© 2026 PharmaAide Clinical Ops. HIPAA Compliant.</div>
          </div>
        </div>
      </footer>
    </div>
  );
};


function UserPlus(props: any) {
  return (
    <svg 
      {...props} 
      xmlns="http://www.w3.org/2000/svg" 
      width="24" 
      height="24" 
      viewBox="0 0 24 24" 
      fill="none" 
      stroke="currentColor" 
      strokeWidth="2" 
      strokeLinecap="round" 
      strokeLinejoin="round"
    >
      <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <line x1="19" y1="8" x2="19" y2="14" />
      <line x1="22" y1="11" x2="16" y2="11" />
    </svg>
  );
}
