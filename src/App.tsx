import { Play } from "lucide-react";
import { useState } from "react";
import "./styles.css";

type Escalation = {
  id: string;
  patientName: string;
  issue: string;
  detail: string;
};

const criticalEscalations: Escalation[] = [
  {
    id: "884-A",
    patientName: "Mary Silva",
    issue: "Consecutive Missed Doses: Apixaban",
    detail: "Last reported vitals irregular. High stroke risk parameter.",
  },
  {
    id: "102-C",
    patientName: "Jonah Davis",
    issue: "Severe Symptom Report: Dyspnea",
    detail: "Patient reported via WhatsApp 14 minutes ago. Current regimen includes Lisinopril.",
  },
];

function maskPatientName(name: string) {
  return name
    .split(" ")
    .map((part) => `${part.charAt(0)}***`)
    .join(" ");
}

function App() {
  const [isPrivacyMode, setIsPrivacyMode] = useState(false);

  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="Primary navigation">
        <div className="sidebar__header">
          <p className="label-caps">PharmaAide</p>
          <p>Clinical Operations</p>
        </div>
        <nav className="sidebar__nav">
          <a className="sidebar__link sidebar__link--active" href="#triage">
            Triage Queue
          </a>
          <a className="sidebar__link" href="#surveillance">
            Patient Surveillance
          </a>
          <a className="sidebar__link" href="#heatmaps">
            Adherence Heatmaps
          </a>
        </nav>
      </aside>

      <main className="workspace">
        <header className="topbar">
          <div>
            <h1>Triage Queue</h1>
          </div>
          <label className="privacy-switch">
            <span className="privacy-switch__label">Privacy Mode</span>
            <input
              checked={isPrivacyMode}
              className="privacy-switch__input"
              onChange={(event) => setIsPrivacyMode(event.target.checked)}
              role="switch"
              type="checkbox"
            />
            <span className="privacy-switch__track" aria-hidden="true">
              <span className="privacy-switch__thumb" />
            </span>
          </label>
        </header>

        <section className="module" aria-labelledby="critical-escalations">
          <div className="module__header">
            <h2 id="critical-escalations">Critical Escalations</h2>
            <span className="status-pill">2 Action Required</span>
          </div>

          <div className="escalation-list">
            {criticalEscalations.map((escalation) => (
              <article className="escalation" key={escalation.id}>
                <div>
                  <p className="patient-ref">Pt. ID: {escalation.id}</p>
                  <p className="patient-name">
                    {isPrivacyMode ? maskPatientName(escalation.patientName) : escalation.patientName}
                  </p>
                  <h3>{escalation.issue}</h3>
                  <p>{escalation.detail}</p>
                </div>
                <button
                  aria-label="Initiate Outreach"
                  className="outreach-button"
                  data-tooltip="Initiate Outreach"
                  type="button"
                >
                  <Play aria-hidden="true" size={18} strokeWidth={2.25} />
                </button>
              </article>
            ))}
          </div>
        </section>
      </main>
    </div>
  );
}

export default App;
