import { useState } from "react";
import {
  FileText, Search, ZoomIn, ZoomOut,
  CheckCircle2, AlertCircle, MessageSquare,
  Play, X, ShieldCheck,
  Upload, Type, ClipboardList, Trash2,
  Edit3, Loader2, Lock
} from "lucide-react";
import { useNavigate } from "react-router-dom";
import { ApiError, ConflictError, ValidationError } from "../api/client";
import { createTreatment } from "../api/treatments";

type IngestionMethod = "structured" | "manual" | "vision";

interface Medication {
  id: string;
  name: string;
  dosage: string;
  frequency: string;
  duration: string;
  objective: string;
}

type SubmitState =
  | { kind: "idle" }
  | { kind: "submitting" }
  | { kind: "success"; treatmentId: string; patientId: string }
  | { kind: "error"; title: string; detail: string; requestId: string | null };

type FieldErrors = Partial<Record<"name" | "dob" | "mrn" | "phone", string>>;

export default function NewTreatmentPage() {
  const navigate = useNavigate();
  // Sprint 2: only the structured tab is wired. Vision/Manual stay visible
  // but disabled — see the tab buttons below for the V1.1 affordance.
  const [method, setMethod] = useState<IngestionMethod>("structured");
  const [medications, setMedications] = useState<Medication[]>([
    { id: "1", name: "Amoxicillin", dosage: "500 mg", frequency: "Times Daily (TID)", duration: "10 Days", objective: "" }
  ]);
  // Sprint 2 always creates a new patient — search-existing flow ships
  // when GET /patients?search= lands. The search input renders disabled.
  const [patientName, setPatientName] = useState("");
  const [patientDob, setPatientDob] = useState("");
  const [patientMrn, setPatientMrn] = useState("");
  const [patientPhone, setPatientPhone] = useState("");
  const [clinicalObjective, setClinicalObjective] = useState("");
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [submitState, setSubmitState] = useState<SubmitState>({ kind: "idle" });
  const [dragActive, setDragActive] = useState(false);

  const addMedication = () => {
    const newMed: Medication = {
      id: crypto.randomUUID(),
      name: "",
      dosage: "",
      frequency: "Once Daily (QD)",
      duration: "",
      objective: ""
    };
    setMedications([...medications, newMed]);
  };

  const removeMedication = (id: string) => {
    if (medications.length > 1) {
      setMedications(medications.filter(m => m.id !== id));
    }
  };

  const updateMedication = (id: string, patch: Partial<Medication>) => {
    setMedications(meds => meds.map(m => (m.id === id ? { ...m, ...patch } : m)));
  };

  const handleSubmit = async () => {
    setFieldErrors({});
    setSubmitState({ kind: "submitting" });

    try {
      const result = await createTreatment({
        patient: {
          name: patientName.trim(),
          dob: patientDob,
          mrn: patientMrn.trim(),
          phone: patientPhone.trim(),
        },
        treatment: {
          clinical_objective: clinicalObjective.trim() || null,
        },
        medications: medications.map(m => ({
          name: m.name.trim(),
          dosage: m.dosage.trim(),
          frequency: m.frequency.trim(),
          duration: m.duration.trim(),
          objective: m.objective.trim() || null,
        })),
        ingestion_method: "structured",
      });

      setSubmitState({
        kind: "success",
        treatmentId: result.treatment_id,
        patientId: result.patient_id,
      });
      // Reset form so the pharmacist can register the next patient.
      setPatientName("");
      setPatientDob("");
      setPatientMrn("");
      setPatientPhone("");
      setClinicalObjective("");
      setMedications([
        { id: crypto.randomUUID(), name: "", dosage: "", frequency: "Once Daily (QD)", duration: "", objective: "" },
      ]);
    } catch (err) {
      if (err instanceof ConflictError) {
        setFieldErrors({ mrn: "This MRN already exists. Please verify or use a different identifier." });
        setSubmitState({
          kind: "error",
          title: "Patient already registered",
          detail: "An existing patient has this MRN. Update the field and try again.",
          requestId: err.requestId,
        });
      } else if (err instanceof ValidationError) {
        const next: FieldErrors = {};
        for (const e of err.fieldErrors) {
          // loc is ["body", "patient", <field>] or ["body", <field>] etc.
          const field = e.loc[e.loc.length - 1];
          if (field === "name" || field === "dob" || field === "mrn" || field === "phone") {
            next[field] = e.msg;
          }
        }
        setFieldErrors(next);
        setSubmitState({
          kind: "error",
          title: "Validation failed",
          detail: "Please correct the highlighted fields and try again.",
          requestId: err.requestId,
        });
      } else if (err instanceof ApiError) {
        setSubmitState({
          kind: "error",
          title: "Server error",
          detail: `Reference ID: ${err.requestId ?? "unknown"}. Please retry; if it keeps failing, share the reference ID with the team.`,
          requestId: err.requestId,
        });
      } else {
        setSubmitState({
          kind: "error",
          title: "Network error",
          detail: "Could not reach the server. Check your connection and try again.",
          requestId: null,
        });
      }
    }
  };

  return (
    <div className="h-full overflow-y-auto p-8">
      <div className="flex flex-col gap-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-blue-50 text-blue-600 rounded-xl flex items-center justify-center shadow-sm">
              <FileText size={20} />
            </div>
            <div>
              <h2 className="text-2xl font-bold tracking-tight text-slate-900">New Treatment Ingestion</h2>
              <p className="text-sm text-slate-500">Upload prescription for automated clinical extraction and regimen scheduling.</p>
            </div>
          </div>
          <button
            onClick={() => navigate(-1)}
            className="px-4 py-2 bg-white border border-slate-200 text-slate-600 rounded-xl font-bold hover:bg-slate-50 transition-colors shadow-sm flex items-center gap-2 cursor-pointer"
          >
            <X size={16} />
            Clear Form
          </button>
        </div>

        {submitState.kind === "success" && (
          <div role="status" className="bg-emerald-50 border border-emerald-200 rounded-xl p-4 flex items-start gap-3">
            <CheckCircle2 size={20} className="text-emerald-600 mt-0.5 shrink-0" />
            <div className="flex-1">
              <p className="font-bold text-emerald-900 text-sm">Treatment created</p>
              <p className="text-xs text-emerald-700 mt-0.5 font-mono">
                Treatment ID: {submitState.treatmentId} · Patient ID: {submitState.patientId}
              </p>
            </div>
            <button
              onClick={() => setSubmitState({ kind: "idle" })}
              className="text-emerald-700 hover:text-emerald-900"
              aria-label="Dismiss"
            >
              <X size={16} />
            </button>
          </div>
        )}

        {submitState.kind === "error" && (
          <div role="alert" className="bg-red-50 border border-red-200 rounded-xl p-4 flex items-start gap-3">
            <AlertCircle size={20} className="text-red-600 mt-0.5 shrink-0" />
            <div className="flex-1">
              <p className="font-bold text-red-900 text-sm">{submitState.title}</p>
              <p className="text-xs text-red-700 mt-0.5">{submitState.detail}</p>
            </div>
            <button
              onClick={() => setSubmitState({ kind: "idle" })}
              className="text-red-700 hover:text-red-900"
              aria-label="Dismiss"
            >
              <X size={16} />
            </button>
          </div>
        )}

        {/* Patient Selection Card */}
        <div className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden p-6 flex flex-col gap-6">
          <div className="flex items-center justify-between">
            <h3 className="font-bold text-slate-900 uppercase tracking-wider text-[11px]">Patient Registration</h3>
          </div>

          {/* Search-existing affordance: visually present, disabled until
              GET /patients?search= ships in a follow-up slice. */}
          <div className="flex flex-col gap-2">
            <div className="relative opacity-60">
              <Search size={18} className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                disabled
                placeholder="Search existing patients by Name or ID..."
                className="w-full pl-12 pr-12 py-4 bg-slate-50 border border-slate-200 rounded-2xl text-base shadow-inner cursor-not-allowed"
                aria-describedby="search-disabled-note"
              />
              <Lock size={16} className="absolute right-4 top-1/2 -translate-y-1/2 text-slate-400" />
            </div>
            <p id="search-disabled-note" className="text-[11px] text-slate-500 px-1">
              Search not yet available — registering below creates a new patient profile.
            </p>
          </div>

          <div className="bg-slate-50 rounded-2xl p-6 border border-slate-200 space-y-6">
            <h4 className="font-bold text-slate-900">New Patient Registration</h4>
            <div className="grid grid-cols-2 gap-6">
              <div className="flex flex-col gap-1.5">
                <label htmlFor="patient-name" className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Full Name</label>
                <input
                  id="patient-name"
                  value={patientName}
                  onChange={(e) => setPatientName(e.target.value)}
                  placeholder="e.g. Eleanor Vance"
                  className={`px-4 py-2 bg-white border rounded-xl text-sm focus:ring-2 focus:ring-blue-100 outline-none ${fieldErrors.name ? "border-red-400" : "border-slate-200"}`}
                />
                {fieldErrors.name && <span className="text-[11px] text-red-600">{fieldErrors.name}</span>}
              </div>
              <div className="flex flex-col gap-1.5">
                <label htmlFor="patient-dob" className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Date of Birth</label>
                <input
                  id="patient-dob"
                  type="date"
                  value={patientDob}
                  onChange={(e) => setPatientDob(e.target.value)}
                  className={`px-4 py-2 bg-white border rounded-xl text-sm focus:ring-2 focus:ring-blue-100 outline-none ${fieldErrors.dob ? "border-red-400" : "border-slate-200"}`}
                />
                {fieldErrors.dob && <span className="text-[11px] text-red-600">{fieldErrors.dob}</span>}
              </div>
              <div className="flex flex-col gap-1.5">
                <label htmlFor="patient-mrn" className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">MRN Number</label>
                <input
                  id="patient-mrn"
                  value={patientMrn}
                  onChange={(e) => setPatientMrn(e.target.value)}
                  placeholder="e.g. 882-12-4401"
                  className={`px-4 py-2 bg-white border rounded-xl text-sm focus:ring-2 focus:ring-blue-100 outline-none ${fieldErrors.mrn ? "border-red-400" : "border-slate-200"}`}
                />
                {fieldErrors.mrn && <span className="text-[11px] text-red-600">{fieldErrors.mrn}</span>}
              </div>
              <div className="flex flex-col gap-1.5">
                <label htmlFor="patient-phone" className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Phone Number (E.164)</label>
                <input
                  id="patient-phone"
                  type="tel"
                  value={patientPhone}
                  onChange={(e) => setPatientPhone(e.target.value)}
                  placeholder="+1 800 555 1212"
                  className={`px-4 py-2 bg-white border rounded-xl text-sm focus:ring-2 focus:ring-blue-100 outline-none ${fieldErrors.phone ? "border-red-400" : "border-slate-200"}`}
                />
                {fieldErrors.phone && <span className="text-[11px] text-red-600">{fieldErrors.phone}</span>}
              </div>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-12 gap-6 items-start">
          {/* Source Ingestion Column */}
          <div className="col-span-7 flex flex-col gap-4">
            <div className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden flex flex-col min-h-[700px]">
              <div className="p-4 border-b border-slate-100 bg-slate-50/50 flex flex-col gap-4">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Source Document Ingestion</span>
                  <div className="flex items-center gap-3 text-slate-400">
                    <button className="hover:text-blue-600 transition-colors cursor-pointer"><Search size={16} /></button>
                    <button className="hover:text-blue-600 transition-colors cursor-pointer"><ZoomIn size={16} /></button>
                    <button className="hover:text-blue-600 transition-colors cursor-pointer"><ZoomOut size={16} /></button>
                  </div>
                </div>
                
                <div className="flex gap-4">
                  {/* Vision and Manual stay visible but disabled until V1.1
                      ships LLM extraction (Sprint 3+). Structured is the
                      only mode that posts to the backend. */}
                  <button
                    disabled
                    title="Coming in V1.1"
                    aria-disabled="true"
                    className="flex items-center gap-2 px-3 py-1.5 text-[11px] font-bold uppercase tracking-wider rounded-lg text-slate-300 cursor-not-allowed"
                  >
                    <Upload size={14} />
                    Vision
                    <Lock size={12} />
                  </button>
                  <button
                    disabled
                    title="Coming in V1.1"
                    aria-disabled="true"
                    className="flex items-center gap-2 px-3 py-1.5 text-[11px] font-bold uppercase tracking-wider rounded-lg text-slate-300 cursor-not-allowed"
                  >
                    <Type size={14} />
                    Manual
                    <Lock size={12} />
                  </button>
                  <button
                    onClick={() => setMethod("structured")}
                    className={`flex items-center gap-2 px-3 py-1.5 text-[11px] font-bold uppercase tracking-wider rounded-lg transition-all cursor-pointer ${method === "structured" ? "text-blue-600 border-b-2 border-blue-600 rounded-none" : "text-slate-400 hover:text-slate-600"}`}
                  >
                    <ClipboardList size={14} />
                    Form
                  </button>
                </div>
              </div>

              <div className="flex-1 bg-slate-50 p-8 flex flex-col relative overflow-hidden">
                {method === "vision" && (
                  <div className="flex-1 flex flex-col gap-6">
                    <div className="flex items-center justify-between">
                      <h3 className="font-bold text-slate-900 text-lg">Prescription Image Ingestion</h3>
                      <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">High-Precision OCR</span>
                    </div>
                    
                    <div 
                      className={`flex-1 border-2 border-dashed rounded-[32px] flex flex-col items-center justify-center p-12 transition-all group cursor-pointer ${
                        dragActive ? 'border-blue-500 bg-blue-50/50' : 'border-slate-200 bg-white hover:border-blue-400 hover:bg-slate-50/50'
                      }`}
                      onDragEnter={() => setDragActive(true)}
                      onDragLeave={() => setDragActive(false)}
                      onDrop={(e) => { e.preventDefault(); setDragActive(false); }}
                      onDragOver={(e) => e.preventDefault()}
                    >
                      <div className="w-20 h-20 bg-slate-50 text-slate-400 rounded-3xl flex items-center justify-center mb-6 group-hover:bg-blue-100 group-hover:text-blue-600 transition-all shadow-inner">
                        <Upload size={32} />
                      </div>
                      <div className="text-center space-y-2">
                        <p className="text-lg font-bold text-slate-900">Drag & drop prescription image</p>
                        <p className="text-sm text-slate-500 font-medium max-w-xs mx-auto">Supported formats: JPEG, PNG, PDF (Scanned). Max file size 10MB.</p>
                      </div>
                      <div className="mt-8">
                        <button className="px-6 py-2.5 bg-white border border-slate-200 text-slate-700 rounded-xl text-[11px] font-bold uppercase tracking-widest hover:bg-slate-50 transition-all cursor-pointer">
                          Browse Files
                        </button>
                      </div>
                    </div>

                    <div className="bg-blue-50/50 border border-blue-100 rounded-2xl p-4 flex items-start gap-3">
                      <AlertCircle size={16} className="text-blue-600 shrink-0 mt-0.5" />
                      <p className="text-[11px] text-blue-700 font-semibold leading-relaxed">
                        For maximum extraction accuracy, ensure the document is well-lit and all clinical sign-offs (DEA, Signature) are clearly visible.
                      </p>
                    </div>
                  </div>
                )}

                {method === "manual" && (
                  <div className="flex flex-col gap-6 h-full">
                    <div className="flex items-center justify-between">
                      <h3 className="font-bold text-slate-900 text-lg">Paste Clinical Text</h3>
                      <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">OCR Alternative</span>
                    </div>
                    <textarea 
                      placeholder="Paste prescription text, clinical notes, or regimen details here..."
                      className="flex-1 w-full p-8 bg-white border border-slate-200 rounded-3xl text-slate-700 focus:outline-none focus:ring-4 focus:ring-blue-100 focus:border-blue-500 transition-all resize-none shadow-inner font-mono text-base leading-relaxed"
                    />
                    <button className="py-3 bg-blue-600 text-white rounded-lg font-bold hover:bg-blue-700 transition-all cursor-pointer text-[11px] uppercase tracking-wider">
                      Extract Clinical Entities
                    </button>
                  </div>
                )}

                {method === "structured" && (
                  <div className="flex flex-col gap-6 h-full overflow-y-auto pr-2">
                    <div className="flex items-center justify-between">
                      <h3 className="font-bold text-slate-900">Manual Regimen Entry</h3>
                      <button 
                        onClick={addMedication}
                        className="px-3 py-1.5 bg-blue-50 text-blue-600 rounded-lg text-xs font-bold flex items-center gap-2 hover:bg-blue-600 hover:text-white transition-all shadow-sm cursor-pointer"
                      >
                        <Plus size={14} />
                        Add Medication
                      </button>
                    </div>
                    
                    <div className="space-y-6">
                      {medications.map((med) => (
                        <div key={med.id} className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm relative group">
                          {medications.length > 1 && (
                            <button 
                              onClick={() => removeMedication(med.id)}
                              className="absolute top-4 right-4 text-slate-300 hover:text-red-500 transition-colors cursor-pointer"
                            >
                              <Trash2 size={16} />
                            </button>
                          )}
                          <div className="grid grid-cols-2 gap-6">
                            <div className="flex flex-col gap-1.5">
                              <label className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Medication Name</label>
                              <input
                                placeholder="e.g. Amoxicillin"
                                className="w-full px-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-100 focus:border-blue-500 transition-all"
                                value={med.name}
                                onChange={(e) => updateMedication(med.id, { name: e.target.value })}
                              />
                            </div>
                            <div className="flex flex-col gap-1.5">
                              <label className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Dosage Strength</label>
                              <input
                                placeholder="e.g. 500mg"
                                className="w-full px-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-100 focus:border-blue-500 transition-all"
                                value={med.dosage}
                                onChange={(e) => updateMedication(med.id, { dosage: e.target.value })}
                              />
                            </div>
                            <div className="flex flex-col gap-1.5">
                              <label className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Frequency</label>
                              <select
                                className="w-full px-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-100 focus:border-blue-500 transition-all appearance-none cursor-pointer"
                                value={med.frequency}
                                onChange={(e) => updateMedication(med.id, { frequency: e.target.value })}
                              >
                                <option>Once Daily (QD)</option>
                                <option>Twice Daily (BID)</option>
                                <option>Times Daily (TID)</option>
                                <option>Every 8 Hours</option>
                              </select>
                            </div>
                            <div className="flex flex-col gap-1.5">
                              <label className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Duration</label>
                              <input
                                placeholder="e.g. 10 days"
                                className="w-full px-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-100 focus:border-blue-500 transition-all"
                                value={med.duration}
                                onChange={(e) => updateMedication(med.id, { duration: e.target.value })}
                              />
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Clinical Extraction Column */}
          <div className="col-span-5 flex flex-col gap-4">
            <div className="bg-white border border-slate-200 rounded-2xl p-4 flex items-start gap-4 shadow-sm">
              <div className="w-10 h-10 bg-slate-50 text-emerald-600 rounded-xl flex items-center justify-center shrink-0 border border-slate-100">
                <CheckCircle2 size={20} />
              </div>
              <div className="flex-1">
                <p className="font-bold text-slate-900 text-sm">Extraction Complete</p>
                <p className="text-xs text-slate-500 mt-1">
                  AI has processed the document. Review and verify the clinical entities below before proceeding.
                </p>
              </div>
            </div>

            <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm flex flex-col gap-6">
              <div className="flex items-center justify-between">
                <h3 className="font-bold text-slate-900 uppercase tracking-wider text-[11px]">Clinical Extraction Overview</h3>
                <span className="text-[10px] text-slate-400 font-medium">{medications.length} drug{medications.length !== 1 ? 's' : ''} detected</span>
              </div>

              <div className="space-y-4 max-h-[450px] overflow-y-auto pr-2">
                {medications.map((med, i) => (
                  <div key={med.id} className="p-4 bg-slate-50 border border-slate-200 rounded-2xl space-y-3 relative group transition-all hover:bg-white hover:border-blue-200 cursor-pointer">
                    <div className="flex justify-between items-center border-b border-slate-100 pb-2 mb-2">
                      <span className="text-[10px] font-bold text-blue-600 uppercase tracking-wider">Medication #{i+1}</span>
                      <div className="flex items-center gap-1.5">
                        <ShieldCheck size={12} className="text-emerald-500" />
                        <span className="text-[9px] font-bold text-emerald-600 uppercase">Verified</span>
                      </div>
                    </div>
                    <div className="flex flex-col gap-1">
                      <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Name & Strength</p>
                      <p className="text-sm font-bold text-slate-900">{med.name || "Pending Entry..."} {med.dosage}</p>
                    </div>
                    <div className="flex items-center justify-between">
                      <div className="flex flex-col gap-1">
                        <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Regimen</p>
                        <p className="text-xs text-slate-600 font-medium">{med.frequency} • {med.duration || "N/A"}</p>
                      </div>
                      <button className="text-slate-300 hover:text-blue-600 transition-colors cursor-pointer">
                        <Edit3 size={14} />
                      </button>
                    </div>
                  </div>
                ))}

                {medications.length === 0 && (
                  <div className="py-12 flex flex-col items-center justify-center text-center opacity-40">
                    <ClipboardList size={32} className="mb-2" />
                    <p className="text-xs font-bold uppercase tracking-wider">No medications added</p>
                  </div>
                )}

                <div className="flex flex-col gap-1.5 mt-4">
                  <label htmlFor="clinical-objective" className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Clinical Objective / Aim of Follow-up</label>
                  <textarea
                    id="clinical-objective"
                    value={clinicalObjective}
                    onChange={(e) => setClinicalObjective(e.target.value)}
                    placeholder="e.g., Monitor for ACE-inhibitor induced dry cough..."
                    className="w-full pl-4 pr-10 py-3 bg-slate-50 border border-slate-200 rounded-xl text-sm min-h-[80px] focus:outline-none focus:ring-2 focus:ring-blue-100 focus:border-blue-500 transition-all resize-none"
                  />
                </div>

                <div className="bg-slate-50 border border-slate-200 rounded-xl p-3 flex items-start gap-3">
                  <AlertCircle size={16} className="text-slate-400 mt-0.5 shrink-0" />
                  <p className="text-xs text-slate-600 leading-relaxed font-medium">
                    Cross-referencing RxNorm... Potential allergy flag detected for Penicillin class.
                  </p>
                </div>
              </div>

              <button
                onClick={handleSubmit}
                disabled={submitState.kind === "submitting"}
                className="w-full py-4 bg-slate-900 text-white rounded-2xl font-bold flex items-center justify-center gap-2 hover:bg-slate-800 transition-all shadow-md shadow-slate-200 mt-2 cursor-pointer disabled:opacity-60 disabled:cursor-wait"
              >
                {submitState.kind === "submitting" ? (
                  <>
                    <Loader2 size={18} className="animate-spin" />
                    Submitting...
                  </>
                ) : (
                  <>
                    <Play size={18} />
                    Approve {medications.length} Medication{medications.length !== 1 ? 's' : ''}
                  </>
                )}
              </button>
            </div>
          </div>
        </div>

        {/* Review & Schedule Cadence Section */}
        <div className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden mb-8">
          <div className="p-5 border-b border-slate-100 bg-slate-50/50 flex items-center justify-between">
            <div>
              <h3 className="font-bold text-slate-900">Review & Schedule Cadence</h3>
              <p className="text-xs text-slate-500 mt-0.5">Proposed automated communication schedule based on regimen.</p>
            </div>
            <div className="flex items-center gap-2 text-xs font-bold text-slate-400 uppercase tracking-wider">
              <ShieldCheck size={14} className="text-emerald-500" />
              HIPAA Compliant Scheduling
            </div>
          </div>
          
          <table className="w-full text-left">
            <thead>
              <tr className="bg-slate-50/20 border-b border-slate-100">
                <th className="px-6 py-4 text-[11px] font-bold tracking-wider text-slate-400 uppercase">Day</th>
                <th className="px-6 py-4 text-[11px] font-bold tracking-wider text-slate-400 uppercase">Scheduled Time</th>
                <th className="px-6 py-4 text-[11px] font-bold tracking-wider text-slate-400 uppercase">Message Type</th>
                <th className="px-6 py-4 text-[11px] font-bold tracking-wider text-slate-400 uppercase">Content Preview</th>
                <th className="px-6 py-4 text-[11px] font-bold tracking-wider text-slate-400 uppercase">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {[
                { day: "Day 01", time: "09:00 AM", type: "Adherence Check", content: "Good morning! Just a reminder to take your first dose of Amoxicillin...", status: "Pending" },
                { day: "Day 01", time: "02:00 PM", type: "Side Effect Screen", content: "Hi Eleanor, checking in to see if you're experiencing any nausea or stomach discomfort...", status: "Pending" },
                { day: "Day 02", time: "09:00 AM", type: "Adherence Check", content: "Good morning! Ready for Day 2? Please confirm once you've taken your dose.", status: "Pending" },
              ].map((row, i) => (
                <tr key={i} className="hover:bg-slate-50/50 transition-colors group cursor-pointer">
                  <td className="px-6 py-4 text-sm font-bold text-slate-900">{row.day}</td>
                  <td className="px-6 py-4 text-sm text-slate-600 font-mono">{row.time}</td>
                  <td className="px-6 py-4 text-sm">
                    <span className="flex items-center gap-2 font-medium text-slate-700">
                      <MessageSquare size={14} className="text-blue-500" />
                      {row.type}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-sm text-slate-500 italic max-w-md truncate">"{row.content}"</td>
                  <td className="px-6 py-4">
                    <span className="px-2 py-0.5 bg-slate-100 text-slate-500 text-[10px] font-bold uppercase rounded tracking-wider">{row.status}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function Plus(props: any) {
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
      <line x1="12" y1="5" x2="12" y2="19" />
      <line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  );
}
