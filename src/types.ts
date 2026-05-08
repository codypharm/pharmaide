export type Page = "triage" | "surveillance" | "heatmaps";

export type EscalationSeverity = "Critical" | "Warning";
export type EscalationFilter = "All" | EscalationSeverity;

export type InterventionPriority = "High" | "Medium" | "Low";
export type InterventionFilter = "All" | InterventionPriority;

export type PatientRisk = "High Risk" | "Elevated" | "Stable";
export type RiskStratification = "High Risk Only" | "Medium to High" | "All Patients";
export type AdherenceStatus = "taken" | "missed" | "no-data";

export type Escalation = {
  id: string;
  patientName: string;
  issue: string;
  detail: string;
  severity: EscalationSeverity;
};

export type Intervention = {
  id: string;
  patientName: string;
  draftPreview: string;
  priority: InterventionPriority;
  draftedAt: string;
};

export type PatientRecord = {
  id: string;
  name: string;
  lastInteraction: string;
  adherenceScore: number;
  riskStatus: PatientRisk;
  latestSignal: string;
};

export type HeatmapRow = {
  patientId: string;
  medicationClass: string;
  riskStatus: PatientRisk;
  adherence: AdherenceStatus[];
};

export type CriticalHeatmapAlert = {
  patientId: string;
  label: string;
  detail: string;
  action: string;
  severity: "critical" | "warning";
};
