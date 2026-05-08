import { Activity, ChevronRight, Filter, Flame, Play, Table2 } from "lucide-react";
import { useState } from "react";
import "./styles.css";

type Page = "triage" | "surveillance";
type EscalationSeverity = "Critical" | "Warning";
type EscalationFilter = "All" | EscalationSeverity;
type InterventionPriority = "High" | "Medium" | "Low";
type InterventionFilter = "All" | InterventionPriority;
type PatientRisk = "High Risk" | "Elevated" | "Stable";

type Escalation = {
  id: string;
  patientName: string;
  issue: string;
  detail: string;
  severity: EscalationSeverity;
};

type Intervention = {
  id: string;
  patientName: string;
  draftPreview: string;
  priority: InterventionPriority;
  draftedAt: string;
};

type PatientRecord = {
  id: string;
  name: string;
  lastInteraction: string;
  adherenceScore: number;
  riskStatus: PatientRisk;
  latestSignal: string;
};

const criticalEscalations: Escalation[] = [
  {
    id: "884-A",
    patientName: "Mary Silva",
    issue: "Consecutive Missed Doses: Apixaban",
    detail: "Last reported vitals irregular. High stroke risk parameter.",
    severity: "Critical",
  },
  {
    id: "102-C",
    patientName: "Jonah Davis",
    issue: "Severe Symptom Report: Dyspnea",
    detail: "Patient reported via WhatsApp 14 minutes ago. Current regimen includes Lisinopril.",
    severity: "Critical",
  },
  {
    id: "941-F",
    patientName: "Amara Lewis",
    issue: "Potential Interaction Flag",
    detail: "New OTC medication reported. Mild interaction risk with existing statin.",
    severity: "Warning",
  },
];

const recentInterventions: Intervention[] = [
  {
    id: "442-B",
    patientName: "Rina Thomas",
    draftPreview: "We noticed you missed your morning dose of Metoprolol. It is important to take this as directed.",
    priority: "Medium",
    draftedAt: "Drafted 5m ago",
  },
  {
    id: "891-K",
    patientName: "Elias Mensah",
    draftPreview: "Your recent blood glucose readings have been consistently high over the last 3 days.",
    priority: "High",
    draftedAt: "Drafted 12m ago",
  },
  {
    id: "220-L",
    patientName: "Sara Patel",
    draftPreview: "Reminder: your Levothyroxine refill is due in 5 days. Reply YES to process.",
    priority: "Low",
    draftedAt: "Drafted 1h ago",
  },
];

const patientRecords: PatientRecord[] = [
  {
    id: "P-8834",
    name: "Thomas Jenkins",
    lastInteraction: "Oct 12, 09:15 AM",
    adherenceScore: 42,
    riskStatus: "High Risk",
    latestSignal: "Two missed Apixaban doses; irregular vitals reported.",
  },
  {
    id: "P-7219",
    name: "Ana Smith",
    lastInteraction: "Oct 11, 14:30 PM",
    adherenceScore: 78,
    riskStatus: "Elevated",
    latestSignal: "Delayed Metoprolol response window.",
  },
  {
    id: "P-9021",
    name: "Kai Lee",
    lastInteraction: "Oct 10, 08:45 AM",
    adherenceScore: 98,
    riskStatus: "Stable",
    latestSignal: "Medication confirmation received on schedule.",
  },
  {
    id: "P-4451",
    name: "Mara Wright",
    lastInteraction: "Oct 09, 11:20 AM",
    adherenceScore: 85,
    riskStatus: "Stable",
    latestSignal: "Refill reminder acknowledged.",
  },
];

function maskPatientName(name: string) {
  return name
    .split(" ")
    .map((part) => `${part.charAt(0)}***`)
    .join(" ");
}

function getPatientInitials(name: string) {
  return name
    .split(" ")
    .map((part) => part.charAt(0))
    .join("")
    .slice(0, 2)
    .toUpperCase();
}

function PatientSurveillancePage({ isPrivacyMode }: { isPrivacyMode: boolean }) {
  return (
    <div className="surveillance-view">
      <section className="module surveillance-module" aria-labelledby="patient-directory">
        <div className="module__header">
          <div>
            <h2 id="patient-directory">Patient Directory</h2>
            <p>Active surveillance roster. Last updated: 14:32 EST</p>
          </div>
          <span className="status-pill status-pill--neutral">124 Patients</span>
        </div>

        <div className="table-wrap">
          <table className="interventions-table surveillance-table">
            <thead>
              <tr>
                <th>Patient ID / Name</th>
                <th>Last Interaction</th>
                <th>Adherence Score</th>
                <th>Risk Status</th>
                <th>Latest Signal</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {patientRecords.map((patient) => (
                <tr className={`risk-row risk-row--${patient.riskStatus.toLowerCase().replace(" ", "-")}`} key={patient.id}>
                  <td>
                    <div className="patient-cell">
                      <span className="patient-avatar" aria-hidden="true">
                        {getPatientInitials(patient.name)}
                      </span>
                      <span>
                        <strong>{patient.id}</strong>
                        <span>{isPrivacyMode ? maskPatientName(patient.name) : patient.name}</span>
                      </span>
                    </div>
                  </td>
                  <td>{patient.lastInteraction}</td>
                  <td>
                    <div className="adherence-score">
                      <span className="adherence-bars" aria-hidden="true">
                        {[20, 40, 60, 80, 100].map((threshold) => (
                          <span
                            className={patient.adherenceScore >= threshold ? "adherence-bar is-filled" : "adherence-bar"}
                            key={threshold}
                          />
                        ))}
                      </span>
                      <strong>{patient.adherenceScore}%</strong>
                    </div>
                  </td>
                  <td>
                    <span className={`risk-chip risk-chip--${patient.riskStatus.toLowerCase().replace(" ", "-")}`}>
                      {patient.riskStatus}
                    </span>
                  </td>
                  <td>{patient.latestSignal}</td>
                  <td>
                    <button aria-label={`Open ${patient.id}`} className="icon-action" type="button">
                      <ChevronRight aria-hidden="true" size={18} strokeWidth={2.1} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="table-footer">
          <span>Showing 1-4 of 124 patients</span>
          <div className="pagination" aria-label="Patient directory pagination">
            <button disabled type="button">1</button>
            <button type="button">2</button>
            <button type="button">3</button>
          </div>
        </div>
      </section>
    </div>
  );
}

function App() {
  const [activePage, setActivePage] = useState<Page>("triage");
  const [isPrivacyMode, setIsPrivacyMode] = useState(false);
  const [escalationFilter, setEscalationFilter] = useState<EscalationFilter>("All");
  const [isEscalationFilterOpen, setIsEscalationFilterOpen] = useState(false);
  const [interventionFilter, setInterventionFilter] = useState<InterventionFilter>("All");
  const [isInterventionFilterOpen, setIsInterventionFilterOpen] = useState(false);
  const visibleEscalations = criticalEscalations.filter((escalation) => {
    return escalationFilter === "All" || escalation.severity === escalationFilter;
  });
  const visibleInterventions = recentInterventions.filter((intervention) => {
    return interventionFilter === "All" || intervention.priority === interventionFilter;
  });
  const pageTitle = activePage === "triage" ? "Triage Queue" : "Patient Surveillance";

  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="Primary navigation">
        <div className="sidebar__header">
          <p className="label-caps">PharmaAide</p>
          <p>Clinical Operations</p>
        </div>
        <nav className="sidebar__nav">
          <a
            aria-current={activePage === "triage" ? "page" : undefined}
            className={`sidebar__link ${activePage === "triage" ? "sidebar__link--active" : ""}`}
            href="#triage"
            onClick={() => setActivePage("triage")}
          >
            <Flame aria-hidden="true" size={18} strokeWidth={2.1} />
            Triage Queue
          </a>
          <a
            aria-current={activePage === "surveillance" ? "page" : undefined}
            className={`sidebar__link ${activePage === "surveillance" ? "sidebar__link--active" : ""}`}
            href="#surveillance"
            onClick={() => setActivePage("surveillance")}
          >
            <Activity aria-hidden="true" size={18} strokeWidth={2.1} />
            Patient Surveillance
          </a>
          <a className="sidebar__link" href="#heatmaps">
            <Table2 aria-hidden="true" size={18} strokeWidth={2.1} />
            Adherence Heatmaps
          </a>
        </nav>
      </aside>

      <main className="workspace">
        <header className="topbar">
          <div>
            <h1>{pageTitle}</h1>
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

        {activePage === "triage" ? (
        <div className="dashboard-grid">
          <div className="alert-banner" role="status">
            System Alert: High volume of missed dose escalations detected. Triage priority adjusted automatically.
          </div>

          <section className="module" aria-labelledby="critical-escalations">
            <div className="module__header">
              <div>
                <h2 id="critical-escalations">Critical Escalations</h2>
                <p>Patients requiring pharmacist intervention.</p>
              </div>
              <div className="module-actions">
                <span className="status-pill">{visibleEscalations.length} Action Required</span>
                <div className="filter-menu">
                  <button
                    aria-expanded={isEscalationFilterOpen}
                    aria-haspopup="menu"
                    aria-label="Filter critical escalations"
                    className="filter-button"
                    onClick={() => setIsEscalationFilterOpen((current) => !current)}
                    type="button"
                  >
                    <Filter aria-hidden="true" size={16} strokeWidth={2.1} />
                    Filter
                  </button>
                  {isEscalationFilterOpen ? (
                    <div className="filter-options" role="menu" aria-label="Critical escalation filters">
                      {(["All", "Critical", "Warning"] as EscalationFilter[]).map((filter) => (
                        <button
                          aria-checked={escalationFilter === filter}
                          className="filter-option"
                          key={filter}
                          onClick={() => {
                            setEscalationFilter(filter);
                            setIsEscalationFilterOpen(false);
                          }}
                          role="menuitemradio"
                          type="button"
                        >
                          {filter}
                        </button>
                      ))}
                    </div>
                  ) : null}
                </div>
              </div>
            </div>

            <div className="escalation-list">
              {visibleEscalations.map((escalation) => (
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

          <section className="side-stack" aria-label="Operations summary">
            <div className="module module--compact" aria-labelledby="system-health">
              <div className="module__header">
                <h2 id="system-health">System Health</h2>
              </div>
              <div className="metric-grid">
                <div className="metric-card">
                  <p className="label-caps">Active Agents</p>
                  <strong>24</strong>
                  <span>/ 25</span>
                </div>
                <div className="metric-card">
                  <p className="label-caps">Queue Load</p>
                  <strong>82%</strong>
                  <div className="progress-track">
                    <div className="progress-fill" />
                  </div>
                </div>
              </div>
              <div className="audit-row">
                <span>Audit Status: Continuous</span>
                <span className="pulse-dot" aria-hidden="true" />
              </div>
            </div>

            <div className="module module--compact" aria-labelledby="quick-actions">
              <div className="module__header">
                <h2 id="quick-actions">Quick Triage Actions</h2>
              </div>
              <div className="quick-actions">
                <button type="button">Force Sync Patient Records</button>
                <button type="button">Generate Shift Handover</button>
              </div>
            </div>
          </section>

          <section className="module interventions-module" aria-labelledby="recent-interventions">
            <div className="module__header">
              <div>
                <h2 id="recent-interventions">Recent Interventions</h2>
                <p>AI-drafted communications pending pharmacist approval.</p>
              </div>
              <div className="module-actions">
                <div className="filter-menu">
                  <button
                    aria-expanded={isInterventionFilterOpen}
                    aria-haspopup="menu"
                    aria-label="Filter recent interventions"
                    className="filter-button"
                    onClick={() => setIsInterventionFilterOpen((current) => !current)}
                    type="button"
                  >
                    <Filter aria-hidden="true" size={16} strokeWidth={2.1} />
                    Filter
                  </button>
                  {isInterventionFilterOpen ? (
                    <div className="filter-options" role="menu" aria-label="Recent intervention filters">
                      {(["All", "High", "Medium", "Low"] as InterventionFilter[]).map((filter) => (
                        <button
                          aria-checked={interventionFilter === filter}
                          className="filter-option"
                          key={filter}
                          onClick={() => {
                            setInterventionFilter(filter);
                            setIsInterventionFilterOpen(false);
                          }}
                          role="menuitemradio"
                          type="button"
                        >
                          {filter}
                        </button>
                      ))}
                    </div>
                  ) : null}
                </div>
              </div>
            </div>
            <div className="table-wrap">
              <table className="interventions-table">
                <thead>
                  <tr>
                    <th>Patient Reference</th>
                    <th>AI Draft Preview</th>
                    <th>Priority</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleInterventions.map((intervention) => (
                    <tr key={intervention.id}>
                      <td>
                        <strong>Pt. ID: {intervention.id}</strong>
                        <span>
                          {isPrivacyMode ? maskPatientName(intervention.patientName) : intervention.patientName}
                        </span>
                      </td>
                      <td>
                        <p>{intervention.draftPreview}</p>
                        <span className="draft-chip">{intervention.draftedAt}</span>
                      </td>
                      <td>
                        <span className={`priority priority--${intervention.priority.toLowerCase()}`}>
                          {intervention.priority}
                        </span>
                      </td>
                      <td>
                        <button className="secondary-action" type="button">Review & Send</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </div>
        ) : (
          <PatientSurveillancePage isPrivacyMode={isPrivacyMode} />
        )}
      </main>
    </div>
  );
}

export default App;
