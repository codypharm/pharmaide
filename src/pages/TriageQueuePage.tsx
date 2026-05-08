import { Filter, Play } from "lucide-react";
import { useState } from "react";
import { criticalEscalations, recentInterventions } from "../data";
import { maskPatientName } from "../privacy";
import type { EscalationFilter, InterventionFilter } from "../types";

type TriageQueuePageProps = {
  isPrivacyMode: boolean;
};

function TriageQueuePage({ isPrivacyMode }: TriageQueuePageProps) {
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

  return (
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
                    <span>{isPrivacyMode ? maskPatientName(intervention.patientName) : intervention.patientName}</span>
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
  );
}

export default TriageQueuePage;
