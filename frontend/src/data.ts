import type { AdherenceStatus, CriticalHeatmapAlert, Escalation, HeatmapRow, Intervention, PatientRecord } from "./types";

export const criticalEscalations: Escalation[] = [
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

export const recentInterventions: Intervention[] = [
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

export const patientRecords: PatientRecord[] = [
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

const fullAdherence = Array(30).fill("taken") as AdherenceStatus[];

export const heatmapRows: HeatmapRow[] = [
  {
    patientId: "PT-8842-A",
    medicationClass: "Anticoagulants",
    riskStatus: "Elevated",
    adherence: [...fullAdherence.slice(0, 24), "missed", ...fullAdherence.slice(25)],
  },
  {
    patientId: "PT-9102-C",
    medicationClass: "Immunosuppressants",
    riskStatus: "Elevated",
    adherence: [
      "taken", "taken", "missed", "taken", "taken", "missed", "taken", "taken", "taken", "taken",
      "taken", "missed", "taken", "taken", "taken", "taken", "taken", "taken", "missed", "missed",
      "taken", "taken", "taken", "taken", "taken", "taken", "taken", "taken", "taken", "taken",
    ],
  },
  {
    patientId: "PT-4410-X",
    medicationClass: "Anticoagulants",
    riskStatus: "High Risk",
    adherence: [
      ...fullAdherence.slice(0, 20),
      "missed", "missed", "missed", "missed", "missed", "missed", "missed", "missed", "no-data", "no-data",
    ],
  },
  {
    patientId: "PT-1123-M",
    medicationClass: "Insulin",
    riskStatus: "Stable",
    adherence: [...fullAdherence.slice(0, 24), "no-data", "no-data", "no-data", "no-data", "no-data", "no-data"],
  },
];

export const criticalHeatmapAlerts: CriticalHeatmapAlert[] = [
  {
    patientId: "PT-4410-X",
    label: "7 Days Missed",
    detail: "Apixaban 5mg BD. High stroke risk parameter active.",
    action: "Direct Triage",
    severity: "critical",
  },
  {
    patientId: "PT-1882-L",
    label: "Erratic",
    detail: "Tacrolimus. Variability > 30% over 14 days. Rejection risk.",
    action: "Direct Triage",
    severity: "critical",
  },
  {
    patientId: "PT-1123-M",
    label: "No Data",
    detail: "Insulin Glargine. Sensor disconnected 6 days.",
    action: "Check Device",
    severity: "warning",
  },
];
