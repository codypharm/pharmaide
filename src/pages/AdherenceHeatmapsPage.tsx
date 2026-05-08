import { ArrowRight, TriangleAlert } from "lucide-react";
import { useState } from "react";
import { criticalHeatmapAlerts, heatmapRows } from "../data";
import type { PatientRisk, RiskStratification } from "../types";

const heatmapDays = Array.from({ length: 30 }, (_, index) => index + 1);

type AdherenceHeatmapsPageProps = {
  isPrivacyMode: boolean;
};

function shouldShowRisk(riskStatus: PatientRisk, riskStratification: RiskStratification) {
  if (riskStratification === "All Patients") {
    return true;
  }

  if (riskStratification === "Medium to High") {
    return riskStatus === "High Risk" || riskStatus === "Elevated";
  }

  return riskStatus === "High Risk";
}

function formatStatus(status: string) {
  return status.replace("-", " ");
}

function AdherenceHeatmapsPage({ isPrivacyMode }: AdherenceHeatmapsPageProps) {
  const [riskStratification, setRiskStratification] = useState<RiskStratification>("High Risk Only");
  const visibleHeatmapRows = heatmapRows.filter((row) => shouldShowRisk(row.riskStatus, riskStratification));

  return (
    <div className="heatmap-view">
      <section className="heatmap-main" aria-label="Heatmap workspace">
        <div className="module heatmap-controls" aria-label="Heatmap controls">
          <div className="heatmap-filter-group">
            <div className="control-field">
              <label className="label-caps" htmlFor="risk-stratification">Risk Stratification</label>
              <select
                id="risk-stratification"
                onChange={(event) => setRiskStratification(event.target.value as RiskStratification)}
                value={riskStratification}
              >
                <option>High Risk Only</option>
                <option>Medium to High</option>
                <option>All Patients</option>
              </select>
            </div>
            <div className="control-field">
              <label className="label-caps" htmlFor="medication-class">Medication Class</label>
              <select id="medication-class" defaultValue="Specific Medications...">
                <option>Specific Medications...</option>
                <option>Anticoagulants</option>
                <option>Immunosuppressants</option>
              </select>
            </div>
          </div>

          <div className="heatmap-legend" aria-label="Heatmap legend">
            <span><i className="legend-key legend-key--taken" />Taken</span>
            <span><i className="legend-key legend-key--missed" />Missed</span>
            <span><i className="legend-key legend-key--no-data" />No Data</span>
          </div>
        </div>

        <section className="module heatmap-module" aria-labelledby="population-heatmap">
          <h2 className="visually-hidden" id="population-heatmap">Population Adherence Heatmap</h2>
          <div className="heatmap-canvas" role="grid" aria-label="Population Adherence Heatmap">
            <div className="heatmap-day-row" role="row">
              <span className="heatmap-patient-spacer" aria-hidden="true" />
              <div className="heatmap-days">
                {heatmapDays.map((day) => (
                  <span className="heatmap-day" key={day}>{[1, 7, 14, 21, 28, 30].includes(day) ? day : ""}</span>
                ))}
              </div>
            </div>

            <div className="heatmap-data-rows">
              {visibleHeatmapRows.map((row) => (
                <div className="heatmap-data-row" role="row" key={row.patientId}>
                  <span className={`heatmap-patient-id ${row.riskStatus === "High Risk" ? "is-critical" : ""}`}>
                    {isPrivacyMode ? "PT-****-*" : row.patientId}
                  </span>
                  <div className="heatmap-cells">
                    {row.adherence.map((status, index) => (
                      <span
                        aria-label={`${row.patientId} day ${index + 1} ${formatStatus(status)}`}
                        className={`heatmap-cell heatmap-cell--${status}`}
                        key={`${row.patientId}-${index}`}
                        role="gridcell"
                      />
                    ))}
                  </div>
                </div>
              ))}
            </div>

            <div className="heatmap-additional-records">
              <span>Showing 146 additional patient records below...</span>
            </div>
          </div>
        </section>
      </section>

      <aside className="module critical-alerts-panel" aria-labelledby="critical-alerts">
        <div className="critical-alerts-header">
          <h2 id="critical-alerts">
            <TriangleAlert aria-hidden="true" size={18} strokeWidth={2.2} />
            Critical Alerts
          </h2>
          <span className="status-pill">3 Actions</span>
        </div>

        <div className="critical-alert-list">
          {criticalHeatmapAlerts.map((alert) => (
            <article className={`critical-alert-card critical-alert-card--${alert.severity}`} key={alert.patientId}>
              <div className="critical-alert-card__topline">
                <strong>{alert.patientId}</strong>
                <span>{alert.label}</span>
              </div>
              <p>{alert.detail}</p>
              <button className="text-icon-button" type="button">
                {alert.action}
                <ArrowRight aria-hidden="true" size={14} strokeWidth={2.2} />
              </button>
            </article>
          ))}
        </div>
      </aside>
    </div>
  );
}

export default AdherenceHeatmapsPage;
