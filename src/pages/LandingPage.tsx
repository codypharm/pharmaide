import {
  ArrowRight,
  Bot,
  ClipboardCheck,
  FileText,
  LockKeyhole,
  MessageCircle,
  Mic,
  Pill,
  Search,
  ShieldCheck,
  Stethoscope,
} from "lucide-react";

type LandingPageProps = {
  onEnterDashboard: () => void;
};

const partnerNames = ["Aegis Health", "MSIA", "AAAIH", "CI-ISAC", "AIDH"];

function LandingPage({ onEnterDashboard }: LandingPageProps) {
  return (
    <div className="landing-shell">
      <header className="landing-header">
        <div className="landing-brand">
          <span className="landing-brand__mark" aria-hidden="true">
            <Pill size={20} strokeWidth={2.2} />
          </span>
          <span>PharmaAide</span>
        </div>
        <nav className="landing-nav" aria-label="Public navigation">
          <a href="#platform">Platform</a>
          <a href="#workflow">Workflow</a>
          <a href="#safety">Privacy and Security</a>
          <a href="#contact">Contact Us</a>
        </nav>
        <div className="landing-header__actions">
          <button className="landing-signin" type="button">Sign in</button>
          <button className="landing-header__cta" type="button">Request Demo</button>
        </div>
      </header>

      <main>
        <section className="landing-hero">
          <div className="landing-hero__content">
            <span className="landing-eyebrow">Clinical Medication Adherence Intelligence</span>
            <h1>The trusted AI for pharmacist-led adherence care</h1>
            <p>
              Add private, secure AI to medication follow-up, patient triage, adherence monitoring, and pharmacist
              oversight.
            </p>
            <div className="landing-actions">
              <button className="landing-primary-action" onClick={onEnterDashboard} type="button">
                Enter Dashboard
                <ArrowRight aria-hidden="true" size={18} strokeWidth={2.2} />
              </button>
            </div>
          </div>

          <div className="landing-trust" aria-label="Trusted by healthcare teams">
            <p>Loved by clinical teams, trusted by adherence programs</p>
            <div>
              {partnerNames.map((name) => (
                <span key={name}>{name}</span>
              ))}
            </div>
          </div>

          <div className="landing-capability-map" aria-label="PharmaAide platform capabilities" id="platform">
            <div className="capability-node capability-node--left capability-node--top">
              <FileText aria-hidden="true" size={18} />
              Treatment Plans
            </div>
            <div className="capability-node capability-node--left capability-node--bottom">
              <Mic aria-hidden="true" size={18} />
              Patient Voice Notes
            </div>

            <div className="capability-core">
              <span aria-hidden="true"><Pill size={28} strokeWidth={2.2} /></span>
              <strong>PharmaAide</strong>
            </div>

            <div className="capability-node capability-node--right capability-node--one">
              <ClipboardCheck aria-hidden="true" size={18} />
              Care Plans
            </div>
            <div className="capability-node capability-node--right capability-node--two">
              <MessageCircle aria-hidden="true" size={18} />
              Consult Notes
            </div>
            <div className="capability-node capability-node--right capability-node--three">
              <Search aria-hidden="true" size={18} />
              Medication Guideline Search
            </div>
            <div className="capability-node capability-node--right capability-node--four">
              <Bot aria-hidden="true" size={18} />
              Differential Triage
            </div>
          </div>
        </section>

        <section className="landing-band" id="workflow">
          <div>
            <span>Closed-loop system</span>
            <h2>From prescription to pharmacist review</h2>
          </div>
          <p>
            PharmaAide connects patient conversations, medication context, and pharmacist review into one operational
            loop. Routine nudges stay quiet; risky patterns are surfaced for human action.
          </p>
        </section>

        <section className="landing-section">
          <div className="workflow-grid">
            <article>
              <Stethoscope aria-hidden="true" size={26} strokeWidth={2.1} />
              <span>01</span>
              <h3>Clinical setup</h3>
              <p>Verify prescriptions, set adherence objectives, and define escalation parameters.</p>
            </article>
            <article className="workflow-card--primary">
              <MessageCircle aria-hidden="true" size={26} strokeWidth={2.1} />
              <span>02</span>
              <h3>Patient engagement</h3>
              <p>Follow up through familiar messaging while monitoring adherence and emerging symptoms.</p>
            </article>
            <article>
              <ShieldCheck aria-hidden="true" size={26} strokeWidth={2.1} />
              <span>03</span>
              <h3>Pharmacist oversight</h3>
              <p>Route critical adherence signals into a review queue with audit-ready context.</p>
            </article>
          </div>
        </section>

        <section className="landing-section" id="safety">
          <div className="landing-section__header">
            <h2>Safety-first clinical guardrails</h2>
            <p>Designed for pharmacist oversight, auditability, and patient-data minimisation.</p>
          </div>
          <div className="feature-grid">
            <article>
              <ShieldCheck aria-hidden="true" size={24} strokeWidth={2.1} />
              <h3>Clinical Intelligence</h3>
              <p>LLM-backed conversation support stays bounded by human-in-the-loop review.</p>
            </article>
            <article>
              <LockKeyhole aria-hidden="true" size={24} strokeWidth={2.1} />
              <h3>Security & Compliance</h3>
              <p>Privacy mode, audit trails, and PHI-aware interface rules shape every workflow.</p>
            </article>
            <article>
              <ClipboardCheck aria-hidden="true" size={24} strokeWidth={2.1} />
              <h3>Patient Oversight</h3>
              <p>Severity-based queues keep the highest-risk adherence events visible.</p>
            </article>
          </div>
        </section>
      </main>
    </div>
  );
}

export default LandingPage;
