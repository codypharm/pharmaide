import { useState, type ChangeEvent, type DragEvent } from "react";
import {
  FileText, Search, ZoomIn, ZoomOut,
  CheckCircle2, AlertCircle, MessageSquare,
  Play, X, ShieldCheck,
  Upload, Type, ClipboardList, Trash2,
  Edit3, Loader2, Lock, Sparkles
} from "lucide-react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { ApiError, ConflictError, ValidationError } from "../api/client";
import { ExtractionError, extractPrescription, type ExtractedPrescription } from "../api/prescriptions";
import { createTreatment, triggerAnalysis } from "../api/treatments";

type IngestionMethod = "structured" | "manual" | "vision";

// Crockford-style alphabet: no I, O, 0, 1 to avoid hand-transcription
// errors when a pharmacist reads the MRN aloud or writes it down.
const MRN_ALPHABET = "ABCDEFGHJKLMNPQRSTVWXYZ23456789";

function generateMrn(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(8));
  let suffix = "";
  for (const b of bytes) {
    suffix += MRN_ALPHABET[b % MRN_ALPHABET.length];
  }
  return `PHA-${suffix}`;
}

interface Medication {
  id: string;
  name: string;
  dosage: string;
  frequency: string;
  duration: string;
}

type FieldErrors = Partial<Record<"name" | "dob" | "mrn" | "phone", string>>;

export default function NewTreatmentPage() {
  const navigate = useNavigate();
  // Vision starts as a local draft source; extraction wiring lands in the
  // next slice so pharmacists can review this upload surface independently.
  const [method, setMethod] = useState<IngestionMethod>("structured");
  const [medications, setMedications] = useState<Medication[]>([
    { id: crypto.randomUUID(), name: "", dosage: "", frequency: "", duration: "" }
  ]);
  // Sprint 2 always creates a new patient — search-existing flow ships
  // when GET /patients?search= lands. The search input renders disabled.
  const [patientName, setPatientName] = useState("");
  const [patientDob, setPatientDob] = useState("");
  const [patientMrn, setPatientMrn] = useState("");
  const [patientPhone, setPatientPhone] = useState("");
  const [clinicalObjective, setClinicalObjective] = useState("");
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const [visionFile, setVisionFile] = useState<File | null>(null);
  const [isExtracting, setIsExtracting] = useState(false);
  const [extractionError, setExtractionError] = useState<string | null>(null);

  const addMedication = () => {
    const newMed: Medication = {
      id: crypto.randomUUID(),
      name: "",
      dosage: "",
      frequency: "",
      duration: "",
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

  const attachVisionFile = (file: File | undefined) => {
    if (file) {
      setVisionFile(file);
      setExtractionError(null);
    }
  };

  const handleVisionFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    attachVisionFile(event.target.files?.[0]);
  };

  const handleVisionDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragActive(false);
    attachVisionFile(event.dataTransfer.files[0]);
  };

  const handleExtractPrescription = async () => {
    if (!visionFile) {
      return;
    }

    setIsExtracting(true);
    setExtractionError(null);
    try {
      const prescription = await extractPrescription(visionFile);
      applyExtractedPrescription(prescription);
      setMethod("structured");
      toast.success("Prescription extracted", {
        description: "Review the prefilled fields before submitting.",
      });
    } catch (err) {
      const message =
        err instanceof ExtractionError
          ? extractionErrorMessage(err.errorCode)
          : "Could not scan this prescription. Try another file or enter it manually.";
      setExtractionError(message);
      toast.error("Extraction failed", { description: message });
    } finally {
      setIsExtracting(false);
    }
  };

  const applyExtractedPrescription = (prescription: ExtractedPrescription) => {
    setPatientName(prescription.patient.name ?? "");
    setPatientDob(prescription.patient.dob ?? "");
    setPatientMrn(prescription.patient.mrn ?? generateMrn());
    setPatientPhone(prescription.patient.phone ?? "");
    setClinicalObjective(prescription.treatment.clinical_objective ?? "");
    setMedications(toMedicationDrafts(prescription));
  };

  const handleSubmit = async () => {
    setShowConfirm(false);
    setFieldErrors({});
    setIsSubmitting(true);

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
          // Per-med objective intentionally omitted — the treatment-level
          // clinical_objective is the single source the agent reads.
          objective: null,
        })),
        ingestion_method: "structured",
      });

      await startInitialAnalysis(result.treatment_id);

      toast.success("Treatment created", {
        description: `Treatment ID: ${result.treatment_id.slice(0, 8)}… · Patient ID: ${result.patient_id.slice(0, 8)}…`,
        duration: 8000,
        action: {
          label: "View",
          onClick: () => navigate(`/dashboard/treatments/${result.treatment_id}`),
        },
      });
      // Reset form so the pharmacist can register the next patient.
      setPatientName("");
      setPatientDob("");
      setPatientMrn("");
      setPatientPhone("");
      setClinicalObjective("");
      setMedications([
        { id: crypto.randomUUID(), name: "", dosage: "", frequency: "", duration: "" },
      ]);
    } catch (err) {
      if (err instanceof ConflictError) {
        setFieldErrors({ mrn: "This MRN already exists. Please verify or use a different identifier." });
        toast.error("Patient already registered", {
          description: "An existing patient has this MRN. Update the field and try again.",
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
        toast.error("Validation failed", {
          description: "Please correct the highlighted fields and try again.",
        });
      } else if (err instanceof ApiError) {
        toast.error("Server error", {
          description: `Reference ID: ${err.requestId ?? "unknown"}. Please retry; if it keeps failing, share the reference ID with the team.`,
        });
      } else {
        toast.error("Network error", {
          description: "Could not reach the server. Check your connection and try again.",
        });
      }
    } finally {
      setIsSubmitting(false);
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

        {/* Shared suggestion list for every medication's frequency input.
            Pharmacists can pick a common sig or type any custom value —
            Sprint 3's schedule generator parses whatever lands here. */}
        <datalist id="frequency-suggestions">
          <option value="Once Daily (QD)" />
          <option value="Twice Daily (BID)" />
          <option value="Three Times Daily (TID)" />
          <option value="Four Times Daily (QID)" />
          <option value="Every 4 Hours (Q4H)" />
          <option value="Every 6 Hours (Q6H)" />
          <option value="Every 8 Hours (Q8H)" />
          <option value="Every 12 Hours (Q12H)" />
          <option value="At Bedtime (QHS)" />
          <option value="As Needed (PRN)" />
          <option value="Once Weekly" />
          <option value="Once Monthly" />
        </datalist>

        {/* Submit feedback now lives in toasts mounted from App.tsx.
            Inline field-level errors below stay (they belong next to the
            input they describe). */}

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
                <div className="flex items-center justify-between">
                  <label htmlFor="patient-mrn" className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">MRN Number</label>
                  <button
                    type="button"
                    onClick={() => setPatientMrn(generateMrn())}
                    className="flex items-center gap-1 text-[10px] font-bold text-blue-600 hover:text-blue-700 uppercase tracking-wider cursor-pointer"
                    title="Mint a new MRN if your institution doesn't issue one"
                  >
                    <Sparkles size={12} />
                    Auto-generate
                  </button>
                </div>
                <input
                  id="patient-mrn"
                  value={patientMrn}
                  onChange={(e) => setPatientMrn(e.target.value)}
                  placeholder="e.g. 882-12-4401 or click Auto-generate"
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
                  <button
                    onClick={() => setMethod("vision")}
                    className={`flex items-center gap-2 px-3 py-1.5 text-[11px] font-bold uppercase tracking-wider rounded-lg transition-all cursor-pointer ${method === "vision" ? "text-blue-600 border-b-2 border-blue-600 rounded-none" : "text-slate-400 hover:text-slate-600"}`}
                  >
                    <Upload size={14} />
                    Vision
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
                      aria-label="Drop prescription file"
                      className={`flex-1 border-2 border-dashed rounded-[32px] flex flex-col items-center justify-center p-12 transition-all group cursor-pointer ${
                        dragActive ? 'border-blue-500 bg-blue-50/50' : 'border-slate-200 bg-white hover:border-blue-400 hover:bg-slate-50/50'
                      }`}
                      onDragEnter={() => setDragActive(true)}
                      onDragLeave={() => setDragActive(false)}
                      onDrop={handleVisionDrop}
                      onDragOver={(e) => e.preventDefault()}
                    >
                      <div className="w-20 h-20 bg-slate-50 text-slate-400 rounded-3xl flex items-center justify-center mb-6 group-hover:bg-blue-100 group-hover:text-blue-600 transition-all shadow-inner">
                        <Upload size={32} />
                      </div>
                      <div className="text-center space-y-2">
                        <p className="text-lg font-bold text-slate-900">
                          {dragActive ? "Release to attach prescription" : "Drag & drop prescription image"}
                        </p>
                        <p className="text-sm text-slate-500 font-medium max-w-xs mx-auto">Supported formats: JPEG, PNG, PDF (Scanned). Max file size 10MB.</p>
                      </div>
                      <div className="mt-8">
                        <label className="px-6 py-2.5 bg-white border border-slate-200 text-slate-700 rounded-xl text-[11px] font-bold uppercase tracking-widest hover:bg-slate-50 transition-all cursor-pointer inline-flex">
                          Browse Files
                          <input
                            aria-label="Browse prescription file"
                            type="file"
                            accept="image/png,image/jpeg,application/pdf"
                            className="sr-only"
                            onChange={handleVisionFileChange}
                          />
                        </label>
                      </div>
                    </div>

                    {visionFile && (
                      <div className="bg-white border border-slate-200 rounded-2xl p-4 flex flex-col gap-4">
                        <div className="flex items-center justify-between gap-4">
                          <div className="min-w-0 flex items-center gap-3">
                            <div className="w-10 h-10 rounded-xl bg-blue-50 text-blue-600 border border-blue-100 flex items-center justify-center shrink-0">
                              <FileText size={18} />
                            </div>
                            <div className="min-w-0">
                              <p className="text-sm font-bold text-slate-900 truncate">
                                {visionFile.name}
                              </p>
                              <p className="text-[11px] font-semibold text-slate-500 tabular-nums">
                                {formatFileSize(visionFile.size)}
                              </p>
                            </div>
                          </div>
                          <span className="text-[10px] font-bold text-blue-700 uppercase tracking-wider bg-blue-50 border border-blue-100 rounded-full px-2.5 py-1">
                            Ready
                          </span>
                        </div>

                        <button
                          type="button"
                          onClick={handleExtractPrescription}
                          disabled={isExtracting}
                          className="w-full py-3 bg-slate-900 text-white rounded-xl text-[11px] font-bold uppercase tracking-widest hover:bg-slate-800 transition-all cursor-pointer disabled:opacity-70 disabled:cursor-wait flex items-center justify-center gap-2"
                        >
                          {isExtracting ? (
                            <>
                              <Loader2 size={16} className="animate-spin" />
                              Scanning Prescription...
                            </>
                          ) : (
                            <>
                              <Sparkles size={16} />
                              Scan &amp; Prefill Form
                            </>
                          )}
                        </button>

                        {extractionError && (
                          <p className="text-xs font-semibold text-red-600">
                            {extractionError}
                          </p>
                        )}
                      </div>
                    )}

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
                              {/* input + datalist: typeahead with common sigs,
                                  but accepts any freetext for prescriptions
                                  that don't fit a canonical pattern. */}
                              <input
                                list="frequency-suggestions"
                                placeholder="e.g. Twice Daily (BID), Every 8 Hours, PRN"
                                className="w-full px-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-100 focus:border-blue-500 transition-all"
                                value={med.frequency}
                                onChange={(e) => updateMedication(med.id, { frequency: e.target.value })}
                              />
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

                    {/* Anchored at the bottom of the list so the
                        pharmacist can add the next medication right
                        where they just finished typing — no scroll-up
                        to the section header. */}
                    <button
                      type="button"
                      onClick={addMedication}
                      className="w-full py-3 border-2 border-dashed border-slate-200 hover:border-blue-400 hover:bg-blue-50/40 text-slate-500 hover:text-blue-700 rounded-2xl text-xs font-bold uppercase tracking-wider flex items-center justify-center gap-2 transition-all cursor-pointer"
                    >
                      <Plus size={14} />
                      Add another medication
                    </button>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Clinical Extraction Column */}
          <div className="col-span-5 flex flex-col gap-4">
            <div className="bg-white border border-slate-200 rounded-2xl p-4 flex items-start gap-4 shadow-sm">
              <div className="w-10 h-10 bg-slate-50 text-slate-500 rounded-xl flex items-center justify-center shrink-0 border border-slate-100">
                <ClipboardList size={20} />
              </div>
              <div className="flex-1">
                <p className="font-bold text-slate-900 text-sm">Regimen Summary</p>
                <p className="text-xs text-slate-500 mt-1">
                  Review the medications and treatment objective below, then submit to create the patient record.
                </p>
              </div>
            </div>

            <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm flex flex-col gap-6">
              <div className="flex items-center justify-between">
                <h3 className="font-bold text-slate-900 uppercase tracking-wider text-[11px]">Clinical Extraction Overview</h3>
                <span className="text-[10px] text-slate-400 font-medium">{medications.filter(m => m.name.trim()).length} medicine{medications.filter(m => m.name.trim()).length !== 1 ? 's' : ''} detected</span>
              </div>

              <div className="space-y-4 max-h-[450px] overflow-y-auto pr-2">
                {medications.map((med, i) => (
                  <div key={med.id} className="p-4 bg-slate-50 border border-slate-200 rounded-2xl space-y-3 relative group transition-all hover:bg-white hover:border-blue-200">
                    <div className="flex justify-between items-center border-b border-slate-100 pb-2 mb-2">
                      <span className="text-[10px] font-bold text-blue-600 uppercase tracking-wider">Medication #{i+1}</span>
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
                  <label htmlFor="clinical-objective" className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">
                    Treatment Objective <span className="text-slate-400 normal-case font-medium tracking-normal">— what the agent should focus on</span>
                  </label>
                  <textarea
                    id="clinical-objective"
                    required
                    value={clinicalObjective}
                    onChange={(e) => setClinicalObjective(e.target.value)}
                    placeholder="e.g. Monitor for ACE-inhibitor cough and dizziness on standing. Confirm the patient takes the morning dose with food."
                    className="w-full pl-4 pr-10 py-3 bg-slate-50 border border-slate-200 rounded-xl text-sm min-h-[80px] focus:outline-none focus:ring-2 focus:ring-blue-100 focus:border-blue-500 transition-all resize-none"
                  />
                  <p className="text-[11px] text-slate-500 px-1">
                    Used to focus the agent's check-in questions throughout the treatment cycle.
                  </p>
                </div>

                <div className="bg-slate-50 border border-slate-200 rounded-xl p-3 flex items-start gap-3">
                  <AlertCircle size={16} className="text-slate-400 mt-0.5 shrink-0" />
                  <p className="text-xs text-slate-500 leading-relaxed font-medium italic">
                    RxNorm grounding and allergy / interaction checks will run when the agent activates this treatment (Sprint 3).
                  </p>
                </div>
              </div>

              <button
                onClick={() => setShowConfirm(true)}
                disabled={isSubmitting}
                className="w-full py-4 bg-slate-900 text-white rounded-2xl font-bold flex items-center justify-center gap-2 hover:bg-slate-800 transition-all shadow-md shadow-slate-200 mt-2 cursor-pointer disabled:opacity-60 disabled:cursor-wait"
              >
                {isSubmitting ? (
                  <>
                    <Loader2 size={18} className="animate-spin" />
                    Submitting...
                  </>
                ) : (
                  <>
                    <Play size={18} />
                    Review &amp; Approve {medications.filter(m => m.name.trim()).length} Medication{medications.filter(m => m.name.trim()).length !== 1 ? 's' : ''}
                  </>
                )}
              </button>
            </div>
          </div>
        </div>

        {/* Schedule preview — populated by Sprint 3 once the schedule
            generator and "Start Cycle" action ship. Today this is an
            honest placeholder, not mock data dressed as real data. */}
        <div className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden mb-8">
          <div className="p-5 border-b border-slate-100 bg-slate-50/50 flex items-center justify-between">
            <div>
              <h3 className="font-bold text-slate-900">Schedule Preview</h3>
              <p className="text-xs text-slate-500 mt-0.5">
                Generated when the pharmacist clicks "Start Cycle" on an active treatment (coming next sprint).
              </p>
            </div>
            <div className="flex items-center gap-2 text-xs font-bold text-slate-400 uppercase tracking-wider">
              <ShieldCheck size={14} className="text-slate-300" />
              Awaiting activation
            </div>
          </div>

          <div className="p-12 flex flex-col items-center justify-center text-center bg-slate-50/30">
            <div className="w-12 h-12 bg-white text-slate-300 rounded-2xl flex items-center justify-center mb-4 border border-slate-100">
              <MessageSquare size={20} />
            </div>
            <p className="text-sm font-bold text-slate-700">No schedule yet</p>
            <p className="text-xs text-slate-500 font-medium max-w-md mt-2">
              The agent's WhatsApp check-in cadence is derived from each medication's frequency × duration once you submit and start the cycle. It will appear here.
            </p>
          </div>
        </div>
      </div>

      {showConfirm && (
        <ConfirmTreatmentModal
          patient={{ name: patientName, dob: patientDob, mrn: patientMrn, phone: patientPhone }}
          objective={clinicalObjective}
          medications={medications.filter(m => m.name.trim())}
          onCancel={() => setShowConfirm(false)}
          onConfirm={handleSubmit}
          submitting={isSubmitting}
        />
      )}
    </div>
  );
}

async function startInitialAnalysis(treatmentId: string): Promise<void> {
  try {
    await triggerAnalysis(treatmentId);
  } catch (err) {
    if (err instanceof ConflictError) {
      return;
    }

    // The treatment is already persisted, so analysis startup is a fallback
    // concern; the Reasoning tab still exposes manual Run Analysis.
    toast.warning("Treatment created, analysis not started", {
      description: "Open the Reasoning tab and run analysis manually if it does not start shortly.",
    });
  }
}

function toMedicationDrafts(prescription: ExtractedPrescription): Medication[] {
  const extracted = prescription.medications.map((medication) => ({
    id: crypto.randomUUID(),
    name: medication.name ?? "",
    dosage: medication.dosage ?? "",
    frequency: medication.frequency ?? "",
    duration: medication.duration ?? "",
  }));

  return extracted.length > 0
    ? extracted
    : [{ id: crypto.randomUUID(), name: "", dosage: "", frequency: "", duration: "" }];
}

function extractionErrorMessage(errorCode: string): string {
  switch (errorCode) {
    case "image_too_large":
      return "The prescription file is larger than 10 MB.";
    case "unsupported_image_type":
      return "Upload a PNG, JPEG, or PDF prescription.";
    case "pdf_render_failed":
      return "This PDF could not be read. Try a clearer scan or use manual entry.";
    case "openai_api_key_missing":
      return "The backend OpenAI API key is not configured.";
    default:
      return "Could not scan this prescription. Try another file or enter it manually.";
  }
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  const kilobytes = bytes / 1024;
  if (kilobytes < 1024) {
    return `${kilobytes.toFixed(1)} KB`;
  }
  return `${(kilobytes / 1024).toFixed(1)} MB`;
}

interface ConfirmTreatmentModalProps {
  patient: { name: string; dob: string; mrn: string; phone: string };
  objective: string;
  medications: Medication[];
  onCancel: () => void;
  onConfirm: () => void;
  submitting: boolean;
}

function ConfirmTreatmentModal({
  patient, objective, medications, onCancel, onConfirm, submitting,
}: ConfirmTreatmentModalProps) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-title"
      className="fixed inset-0 z-50 flex items-center justify-center p-6 bg-slate-900/50 backdrop-blur-sm"
      onClick={onCancel}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="bg-white rounded-2xl shadow-2xl border border-slate-200 max-w-2xl w-full max-h-[90vh] flex flex-col"
      >
        <div className="p-6 border-b border-slate-100 flex items-start justify-between">
          <div>
            <h2 id="confirm-title" className="font-bold text-slate-900 text-lg">Confirm treatment</h2>
            <p className="text-xs text-slate-500 mt-1">
              Review the entered data. Once confirmed, the patient and treatment records are created in the database.
            </p>
          </div>
          <button
            onClick={onCancel}
            className="text-slate-400 hover:text-slate-700 transition-colors cursor-pointer"
            aria-label="Close confirmation"
          >
            <X size={20} />
          </button>
        </div>

        <div className="p-6 overflow-y-auto flex flex-col gap-6">
          <section>
            <h3 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-3">Patient</h3>
            <div className="bg-slate-50 border border-slate-100 rounded-xl p-4 grid grid-cols-2 gap-y-2 gap-x-6 text-sm">
              <div><span className="text-slate-500">Name:</span> <span className="font-bold text-slate-900">{patient.name || "—"}</span></div>
              <div><span className="text-slate-500">DOB:</span> <span className="font-mono text-slate-900">{patient.dob || "—"}</span></div>
              <div><span className="text-slate-500">MRN:</span> <span className="font-mono text-slate-900">{patient.mrn || "—"}</span></div>
              <div><span className="text-slate-500">Phone:</span> <span className="font-mono text-slate-900">{patient.phone || "—"}</span></div>
            </div>
          </section>

          <section>
            <h3 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-3">Treatment Objective</h3>
            <div className="bg-slate-50 border border-slate-100 rounded-xl p-4 text-sm text-slate-700 italic">
              {objective.trim() ? `"${objective.trim()}"` : <span className="text-slate-400 not-italic">No objective entered.</span>}
            </div>
          </section>

          <section>
            <h3 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-3">
              Medications ({medications.length})
            </h3>
            {medications.length === 0 ? (
              <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 text-sm text-amber-800">
                No medications entered. Add at least one before confirming.
              </div>
            ) : (
              <div className="flex flex-col gap-2">
                {medications.map((m, i) => (
                  <div key={m.id} className="bg-slate-50 border border-slate-100 rounded-xl p-4 text-sm">
                    <div className="flex items-baseline justify-between mb-1">
                      <span className="text-[10px] font-bold text-blue-600 uppercase tracking-wider">#{i + 1}</span>
                      <span className="font-bold text-slate-900">{m.name} {m.dosage}</span>
                    </div>
                    <div className="text-xs text-slate-600 text-right">
                      {m.frequency || "—"} · {m.duration || "—"}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>

        <div className="p-6 border-t border-slate-100 flex items-center justify-between gap-3">
          <button
            onClick={onCancel}
            disabled={submitting}
            className="px-5 py-2.5 bg-white border border-slate-200 text-slate-700 rounded-xl font-bold text-sm hover:bg-slate-50 transition-all disabled:opacity-50 cursor-pointer"
          >
            Cancel &amp; edit
          </button>
          <button
            onClick={onConfirm}
            disabled={submitting || medications.length === 0}
            className="px-6 py-2.5 bg-slate-900 text-white rounded-xl font-bold text-sm flex items-center gap-2 hover:bg-slate-800 transition-all shadow-md disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
          >
            {submitting ? (
              <>
                <Loader2 size={16} className="animate-spin" />
                Submitting…
              </>
            ) : (
              <>
                <CheckCircle2 size={16} />
                Confirm &amp; create
              </>
            )}
          </button>
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
