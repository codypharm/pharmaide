import {
  Activity,
  ArrowRight,
  Database,
  MessageSquareWarning,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";
import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";

import landingHeroImage from "../assets/landing-hero.jpg";

const capabilities: Array<{
  icon: LucideIcon;
  title: string;
  text: string;
}> = [
  {
    icon: Activity,
    title: "Patient surveillance",
    text: "Follow active treatments, patient updates, adherence signals, and pharmacist takeovers from one clinical workspace.",
  },
  {
    icon: MessageSquareWarning,
    title: "Human review queue",
    text: "Hold uncertain patient-facing drafts until the pharmacist approves, edits, or rejects the response.",
  },
  {
    icon: Database,
    title: "Grounded guidance",
    text: "Use clinic protocols, treatment context, RxNorm grounding, and DailyMed references to support safer follow-up.",
  },
];

const workflow = [
  "Patient messages arrive through WhatsApp",
  "Agent drafts are checked before patient delivery",
  "Pharmacists approve, reject, or take over the conversation",
];

export default function LandingPage() {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-[#F5F5F6] font-['Public_Sans'] text-slate-950">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
          <button
            type="button"
            onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
            className="flex items-center gap-3 text-left cursor-pointer"
          >
            <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-[#5548E8] text-white">
              <ShieldCheck size={19} />
            </span>
            <span>
              <span className="block text-sm font-black tracking-tight">PharmaAide</span>
              <span className="block text-[10px] font-bold uppercase tracking-wider text-slate-500">
                Clinical operations
              </span>
            </span>
          </button>

          <nav className="hidden items-center gap-6 text-xs font-bold uppercase tracking-wider text-slate-500 md:flex">
            <a href="#capabilities" className="hover:text-slate-950">
              Capabilities
            </a>
            <a href="#safety" className="hover:text-slate-950">
              Safety
            </a>
            <a href="#workflow" className="hover:text-slate-950">
              Workflow
            </a>
          </nav>

          <button
            type="button"
            onClick={() => navigate("/dashboard/triage")}
            className="inline-flex items-center gap-2 rounded-lg border border-[#5548E8] bg-[#5548E8] px-4 py-2 text-sm font-bold text-white transition-colors hover:bg-[#463AD4] cursor-pointer"
          >
            Review Triage
            <ArrowRight size={15} />
          </button>
        </div>
      </header>

      <main>
        <section className="border-b border-slate-200 bg-white">
          <div className="mx-auto grid max-w-7xl gap-10 px-6 py-16 md:py-20 lg:grid-cols-[0.9fr_1.1fr] lg:items-center">
            <div>
              <p className="mb-4 inline-flex rounded-full border border-[#D9D5FB] bg-[#F0EFFF] px-3 py-1 text-[11px] font-bold uppercase tracking-wider text-[#463AD4]">
                Pharmacist-in-the-loop medication support
              </p>
              <h1 className="max-w-3xl text-4xl font-black leading-tight tracking-tight text-slate-950 md:text-6xl">
                PharmaAide keeps patient conversations clinically supervised.
              </h1>
              <p className="mt-6 max-w-2xl text-base leading-7 text-slate-700">
                A medication follow-up workspace where AI drafts, pharmacists review,
                and every patient-facing response stays inside a safety-first workflow.
              </p>

              <div className="mt-8 flex flex-col gap-3 sm:flex-row">
                <button
                  type="button"
                  onClick={() => navigate("/dashboard/triage")}
                  className="inline-flex items-center justify-center gap-2 rounded-lg border border-[#5548E8] bg-[#5548E8] px-5 py-3 text-sm font-bold text-white transition-colors hover:bg-[#463AD4] cursor-pointer"
                >
                  Review Triage
                  <MessageSquareWarning size={16} />
                </button>
                <button
                  type="button"
                  onClick={() => navigate("/dashboard/surveillance")}
                  className="inline-flex items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-5 py-3 text-sm font-bold text-slate-900 transition-colors hover:bg-slate-50 cursor-pointer"
                >
                  Open Surveillance
                  <Activity size={16} />
                </button>
              </div>
            </div>

            <div className="overflow-hidden rounded-lg border border-slate-200 bg-slate-50">
              <img
                src={landingHeroImage}
                alt="PharmaAide pharmacist monitoring dashboard and patient chatbot workflow"
                className="block aspect-[4/3] h-auto w-full object-contain object-center lg:aspect-[5/4]"
              />
            </div>
          </div>
        </section>

        <section id="capabilities" className="border-y border-slate-200 bg-white">
          <div className="mx-auto max-w-7xl px-6 py-10">
            <div className="max-w-2xl">
              <p className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
                Built for pharmacy teams
              </p>
              <h2 className="mt-2 text-3xl font-black tracking-tight text-slate-950">
                Supervised automation for medication follow-up.
              </h2>
              <p className="mt-3 text-sm leading-6 text-slate-600">
                Designed for pharmacists who need patient messaging, clinical
                review, and medication follow-up in the same controlled workflow.
              </p>
            </div>

            <div className="mt-6 grid gap-4 md:grid-cols-3">
              {capabilities.map((item) => (
                <CapabilityCard key={item.title} item={item} />
              ))}
            </div>
          </div>
        </section>

        <section id="safety" className="mx-auto grid max-w-7xl gap-6 px-6 py-10 lg:grid-cols-2">
          <InfoPanel
            icon={<ShieldCheck size={20} />}
            title="Safety stays before delivery"
            text="Patient-facing drafts are validated, held when uncertain, and routed to pharmacist review before they can be sent."
          />
          <InfoPanel
            icon={<Database size={20} />}
            title="Grounded by clinic context"
            text="Treatment analysis can cite clinic-uploaded knowledge and public DailyMed references without exposing patient text in audit logs."
          />
        </section>

        <section id="workflow" className="mx-auto max-w-7xl px-6 pb-14">
          <div className="rounded-lg border border-slate-200 bg-white p-6">
            <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
              <div>
                <p className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
                  Operating model
                </p>
                <h2 className="mt-2 text-2xl font-black tracking-tight text-slate-950">
                  AI assists. Pharmacists stay in control.
                </h2>
              </div>
              <button
                type="button"
                onClick={() => navigate("/dashboard/triage")}
                className="inline-flex w-fit items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-bold text-slate-900 transition-colors hover:bg-slate-50 cursor-pointer"
              >
                Review flagged drafts
                <ArrowRight size={15} />
              </button>
            </div>
            <ol className="mt-6 grid gap-3 md:grid-cols-3">
              {workflow.map((step, index) => (
                <li key={step} className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                  <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
                    Step {index + 1}
                  </span>
                  <p className="mt-2 text-sm font-semibold leading-6 text-slate-900">{step}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>
      </main>
    </div>
  );
}

function CapabilityCard({
  item,
}: {
  item: {
    icon: LucideIcon;
    title: string;
    text: string;
  };
}) {
  const Icon = item.icon;

  return (
    <article className="rounded-lg border border-slate-200 bg-white p-5">
      <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-[#D9D5FB] bg-[#F0EFFF] text-[#5548E8]">
        <Icon size={19} />
      </div>
      <h3 className="mt-5 text-lg font-black tracking-tight text-slate-950">{item.title}</h3>
      <p className="mt-3 text-sm leading-6 text-slate-600">{item.text}</p>
    </article>
  );
}

function InfoPanel({
  icon,
  title,
  text,
}: {
  icon: ReactNode;
  title: string;
  text: string;
}) {
  return (
    <article className="rounded-lg border border-slate-200 bg-white p-6">
      <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-[#D9D5FB] bg-[#F0EFFF] text-[#5548E8]">
        {icon}
      </div>
      <h2 className="mt-5 text-xl font-black tracking-tight text-slate-950">{title}</h2>
      <p className="mt-3 text-sm leading-6 text-slate-600">{text}</p>
    </article>
  );
}
