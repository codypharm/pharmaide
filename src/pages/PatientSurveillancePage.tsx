import { ChevronRight } from "lucide-react";
import { patientRecords } from "../data";
import { getPatientInitials, maskPatientName } from "../privacy";

type PatientSurveillancePageProps = {
  isPrivacyMode: boolean;
};

function riskClassName(riskStatus: string) {
  return riskStatus.toLowerCase().replace(" ", "-");
}

function PatientSurveillancePage({ isPrivacyMode }: PatientSurveillancePageProps) {
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
                <tr className={`risk-row risk-row--${riskClassName(patient.riskStatus)}`} key={patient.id}>
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
                    <span className={`risk-chip risk-chip--${riskClassName(patient.riskStatus)}`}>
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

export default PatientSurveillancePage;
