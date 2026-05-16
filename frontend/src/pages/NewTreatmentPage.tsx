import { useState, type ChangeEvent, type DragEvent, type KeyboardEvent } from "react";
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
import { createTreatment } from "../api/treatments";

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

type FieldErrors = Partial<Record<"name" | "dob" | "mrn" | "phone" | "allergies", string>>;
type ExtractionFieldKey = string;
type ExtractionErrorState = { message: string; requestId: string | null };

const extractedFieldClass = "border-[#5548E8] bg-[#F0EFFF]";
const lowConfidenceFieldClass = "border-amber-500 bg-amber-50/40";
const LOW_CONFIDENCE_THRESHOLD = 0.7;
const LOW_CONFIDENCE_TITLE = "AI confidence low - verify";

export default function NewTreatmentPage() {
  const navigate = useNavigate();
  // Vision starts as a local draft source; extraction wiring lands in the
  // next slice so pharmacists can review this upload surface independently.
  const [method, setMethod] = useState<IngestionMethod>("structured");
  const [ingestionSource, setIngestionSource] = useState<IngestionMethod>("structured");
  const [medications, setMedications] = useState<Medication[]>([
    { id: crypto.randomUUID(), name: "", dosage: "", frequency: "", duration: "" }
  ]);
  // Sprint 2 always creates a new patient — search-existing flow ships
  // when GET /patients?search= lands. The search input renders disabled.
  const [patientName, setPatientName] = useState("");
  const [patientDob, setPatientDob] = useState("");
  const [patientMrn, setPatientMrn] = useState("");
  const [patientPhone, setPatientPhone] = useState("");
  const [patientAllergies, setPatientAllergies] = useState<string[]>([]);
  const [allergyDraft, setAllergyDraft] = useState("");
  const [clinicalObjective, setClinicalObjective] = useState("");
  const [treatmentStartAt, setTreatmentStartAt] = useState("");
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [manualText, setManualText] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const [visionFile, setVisionFile] = useState<File | null>(null);
  const [isExtracting, setIsExtracting] = useState(false);
  const [extractionError, setExtractionError] = useState<ExtractionErrorState | null>(null);
  const [extractionWarnings, setExtractionWarnings] = useState<string[]>([]);
  const [extractedFields, setExtractedFields] = useState<Set<ExtractionFieldKey>>(
    () => new Set(),
  );
  const [lowConfidenceFields, setLowConfidenceFields] = useState<Set<ExtractionFieldKey>>(
    () => new Set(),
  );
  const currentPatientAllergies = appendPatientAllergies(patientAllergies, allergyDraft);

  const resetDraft = () => {
    setMethod("structured");
    setIngestionSource("structured");
    setMedications([
      { id: crypto.randomUUID(), name: "", dosage: "", frequency: "", duration: "" },
    ]);
    setPatientName("");
    setPatientDob("");
    setPatientMrn("");
    setPatientPhone("");
    setPatientAllergies([]);
    setAllergyDraft("");
    setClinicalObjective("");
    setTreatmentStartAt("");
    setFieldErrors({});
    setManualText("");
    setShowConfirm(false);
    setDragActive(false);
    setVisionFile(null);
    setExtractionError(null);
    setExtractionWarnings([]);
    setExtractedFields(new Set());
    setLowConfidenceFields(new Set());
  };

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

  const addPatientAllergy = () => {
    const next = appendPatientAllergies(patientAllergies, allergyDraft);
    if (next.length !== patientAllergies.length) {
      setPatientAllergies(next);
    }
    setAllergyDraft("");
  };

  const removePatientAllergy = (allergy: string) => {
    setPatientAllergies((allergies) => allergies.filter((entry) => entry !== allergy));
  };

  const handleAllergyKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter" || event.key === ",") {
      event.preventDefault();
      addPatientAllergy();
    }
  };

  const clearExtractedField = (key: ExtractionFieldKey) => {
    setExtractedFields((current) => {
      if (!current.has(key)) {
        return current;
      }
      const next = new Set(current);
      next.delete(key);
      return next;
    });
    setLowConfidenceFields((current) => {
      if (!current.has(key)) {
        return current;
      }
      const next = new Set(current);
      next.delete(key);
      return next;
    });
  };

  const updateMedication = (id: string, patch: Partial<Medication>) => {
    setMedications(meds => meds.map(m => (m.id === id ? { ...m, ...patch } : m)));
    for (const field of Object.keys(patch)) {
      clearExtractedField(medicationFieldKey(id, field as keyof Medication));
    }
  };

  const attachVisionFile = (file: File | undefined) => {
    if (file) {
      setVisionFile(file);
      setExtractionError(null);
      setExtractionWarnings([]);
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
    setExtractionWarnings([]);
    try {
      const prescription = await extractPrescription(visionFile);
      applyExtractedPrescription(prescription);
      setIngestionSource("vision");
      setMethod("structured");
      toast.success("Prescription extracted", {
        description: "Review the prefilled fields before submitting.",
      });
    } catch (err) {
      const message =
        err instanceof ExtractionError
          ? extractionErrorMessage(err.errorCode)
          : "Could not scan this prescription. Try another file or enter it manually.";
      setExtractionError({
        message,
        requestId: err instanceof ExtractionError ? err.requestId : null,
      });
      toast.error("Extraction failed", { description: message });
    } finally {
      setIsExtracting(false);
    }
  };

  const applyExtractedPrescription = (prescription: ExtractedPrescription) => {
    const medicationDrafts = toMedicationDrafts(prescription);
    setPatientName(prescription.patient.name ?? "");
    setPatientDob(prescription.patient.dob ?? "");
    setPatientMrn(prescription.patient.mrn ?? generateMrn());
    setPatientPhone(prescription.patient.phone ?? "");
    setClinicalObjective(prescription.treatment.clinical_objective ?? "");
    setMedications(medicationDrafts);
    setExtractedFields(extractedFieldKeys(prescription, medicationDrafts));
    setLowConfidenceFields(lowConfidenceFieldKeys(prescription, medicationDrafts));
    setExtractionWarnings(prescription.warnings);
  };

  const handleManualExtraction = () => {
    const medicationDrafts = parseManualMedicationText(manualText);
    if (medicationDrafts.length === 0) {
      toast.warning("No medication lines found", {
        description: "Paste one medication per line, then try again.",
      });
      return;
    }

    setMedications(medicationDrafts);
    setIngestionSource("manual");
    setExtractionError(null);
    setExtractionWarnings([]);
    setExtractedFields(new Set());
    setLowConfidenceFields(new Set());
    setMethod("structured");
    toast.success("Manual text parsed", {
      description: "Review the medications before submitting.",
    });
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
          allergies: currentPatientAllergies,
        },
        treatment: {
          clinical_objective: clinicalObjective.trim() || null,
          treatment_start_at: toTreatmentStartIso(treatmentStartAt),
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
        ingestion_method: ingestionSource,
      });

      toast.success("Treatment created", {
        description: treatmentCreatedDescription(result),
        duration: 8000,
        action: {
          label: "View",
          onClick: () => navigate(`/dashboard/treatments/${result.treatment_id}`),
        },
      });
      // Reset form so the pharmacist can register the next patient.
      resetDraft();
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
          if (
            field === "name" ||
            field === "dob" ||
            field === "mrn" ||
            field === "phone" ||
            field === "allergies"
          ) {
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
            <div className="w-10 h-10 bg-[#F0EFFF] text-[#5548E8] rounded-xl flex items-center justify-center shadow-sm">
              <FileText size={20} />
            </div>
            <div>
              <h2 className="text-2xl font-bold tracking-tight text-slate-900">New Treatment Ingestion</h2>
              <p className="text-sm text-slate-500">Upload prescription for automated clinical extraction and regimen scheduling.</p>
            </div>
          </div>
          <button
            type="button"
            onClick={resetDraft}
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
                  onChange={(e) => {
                    setPatientName(e.target.value);
                    clearExtractedField("patient.name");
                  }}
                  placeholder="e.g. Eleanor Vance"
                  data-extraction-origin={extractedFields.has("patient.name") ? "vision" : undefined}
                  data-extraction-confidence={lowConfidenceAttribute(lowConfidenceFields, "patient.name")}
                  title={lowConfidenceTitle(lowConfidenceFields, "patient.name")}
                  className={`px-4 py-2 bg-white border rounded-xl text-sm focus:ring-2 focus:ring-[#D9D5FB] outline-none ${fieldErrors.name ? "border-red-400" : extractionFieldClass(extractedFields, lowConfidenceFields, "patient.name", "border-slate-200")}`}
                />
                {fieldErrors.name && <span className="text-[11px] text-red-600">{fieldErrors.name}</span>}
              </div>
              <div className="flex flex-col gap-1.5">
                <label htmlFor="patient-dob" className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Date of Birth</label>
                <input
                  id="patient-dob"
                  type="date"
                  value={patientDob}
                  onChange={(e) => {
                    setPatientDob(e.target.value);
                    clearExtractedField("patient.dob");
                  }}
                  data-extraction-origin={extractedFields.has("patient.dob") ? "vision" : undefined}
                  data-extraction-confidence={lowConfidenceAttribute(lowConfidenceFields, "patient.dob")}
                  title={lowConfidenceTitle(lowConfidenceFields, "patient.dob")}
                  className={`px-4 py-2 bg-white border rounded-xl text-sm focus:ring-2 focus:ring-[#D9D5FB] outline-none ${fieldErrors.dob ? "border-red-400" : extractionFieldClass(extractedFields, lowConfidenceFields, "patient.dob", "border-slate-200")}`}
                />
                {fieldErrors.dob && <span className="text-[11px] text-red-600">{fieldErrors.dob}</span>}
              </div>
              <div className="flex flex-col gap-1.5">
                <div className="flex items-center justify-between">
                  <label htmlFor="patient-mrn" className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">MRN Number</label>
                  <button
                    type="button"
                    onClick={() => setPatientMrn(generateMrn())}
                    className="flex items-center gap-1 text-[10px] font-bold text-[#5548E8] hover:text-[#463AD4] uppercase tracking-wider cursor-pointer"
                    title="Mint a new MRN if your institution doesn't issue one"
                  >
                    <Sparkles size={12} />
                    Auto-generate
                  </button>
                </div>
                <input
                  id="patient-mrn"
                  value={patientMrn}
                  onChange={(e) => {
                    setPatientMrn(e.target.value);
                    clearExtractedField("patient.mrn");
                  }}
                  placeholder="e.g. 882-12-4401 or click Auto-generate"
                  data-extraction-origin={extractedFields.has("patient.mrn") ? "vision" : undefined}
                  data-extraction-confidence={lowConfidenceAttribute(lowConfidenceFields, "patient.mrn")}
                  title={lowConfidenceTitle(lowConfidenceFields, "patient.mrn")}
                  className={`px-4 py-2 bg-white border rounded-xl text-sm focus:ring-2 focus:ring-[#D9D5FB] outline-none ${fieldErrors.mrn ? "border-red-400" : extractionFieldClass(extractedFields, lowConfidenceFields, "patient.mrn", "border-slate-200")}`}
                />
                {fieldErrors.mrn && <span className="text-[11px] text-red-600">{fieldErrors.mrn}</span>}
              </div>
              <div className="flex flex-col gap-1.5">
                <label htmlFor="patient-phone" className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Phone Number (E.164)</label>
                <input
                  id="patient-phone"
                  type="tel"
                  value={patientPhone}
                  onChange={(e) => {
                    setPatientPhone(e.target.value);
                    clearExtractedField("patient.phone");
                  }}
                  placeholder="+1 800 555 1212"
                  data-extraction-origin={extractedFields.has("patient.phone") ? "vision" : undefined}
                  data-extraction-confidence={lowConfidenceAttribute(lowConfidenceFields, "patient.phone")}
                  title={lowConfidenceTitle(lowConfidenceFields, "patient.phone")}
                  className={`px-4 py-2 bg-white border rounded-xl text-sm focus:ring-2 focus:ring-[#D9D5FB] outline-none ${fieldErrors.phone ? "border-red-400" : extractionFieldClass(extractedFields, lowConfidenceFields, "patient.phone", "border-slate-200")}`}
                />
                {fieldErrors.phone && <span className="text-[11px] text-red-600">{fieldErrors.phone}</span>}
              </div>
              <div className="flex flex-col gap-1.5 col-span-2">
                <label htmlFor="allergy-name" className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Allergy Name</label>
                <div className="flex gap-2">
                  <input
                    id="allergy-name"
                    value={allergyDraft}
                    onChange={(e) => setAllergyDraft(e.target.value)}
                    onKeyDown={handleAllergyKeyDown}
                    placeholder="e.g. Penicillin"
                    className={`min-w-0 flex-1 px-4 py-2 bg-white border rounded-xl text-sm focus:ring-2 focus:ring-[#D9D5FB] outline-none ${fieldErrors.allergies ? "border-red-400" : "border-slate-200"}`}
                  />
                  <button
                    type="button"
                    onClick={addPatientAllergy}
                    disabled={!allergyDraft.trim()}
                    className="px-4 py-2 bg-slate-900 text-white rounded-xl text-[11px] font-bold uppercase tracking-widest hover:bg-slate-800 transition-all disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
                  >
                    Add Allergy
                  </button>
                </div>
                {patientAllergies.length > 0 && (
                  <div className="flex flex-wrap gap-2">
                    {patientAllergies.map((allergy) => (
                      <span
                        key={allergy}
                        className="inline-flex items-center gap-1.5 rounded-full border border-red-200 bg-red-50 px-2.5 py-1 text-[11px] font-bold text-red-700"
                      >
                        {allergy}
                        <button
                          type="button"
                          onClick={() => removePatientAllergy(allergy)}
                          className="text-red-500 hover:text-red-800 cursor-pointer"
                          aria-label={`Remove ${allergy}`}
                        >
                          <X size={12} />
                        </button>
                      </span>
                    ))}
                  </div>
                )}
                {fieldErrors.allergies ? (
                  <span className="text-[11px] text-red-600">{fieldErrors.allergies}</span>
                ) : (
                  <span className="text-[11px] text-slate-500">
                    Add one substance at a time. Keep reaction notes out of this field.
                  </span>
                )}
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
                    <button className="hover:text-[#5548E8] transition-colors cursor-pointer"><Search size={16} /></button>
                    <button className="hover:text-[#5548E8] transition-colors cursor-pointer"><ZoomIn size={16} /></button>
                    <button className="hover:text-[#5548E8] transition-colors cursor-pointer"><ZoomOut size={16} /></button>
                  </div>
                </div>
                
                <div className="flex gap-4">
                  <button
                    onClick={() => setMethod("vision")}
                    className={`flex items-center gap-2 px-3 py-1.5 text-[11px] font-bold uppercase tracking-wider rounded-lg transition-all cursor-pointer ${method === "vision" ? "text-[#5548E8] border-b-2 border-[#5548E8] rounded-none" : "text-slate-400 hover:text-slate-600"}`}
                  >
                    <Upload size={14} />
                    Vision
                  </button>
                  <button
                    onClick={() => setMethod("manual")}
                    className={`flex items-center gap-2 px-3 py-1.5 text-[11px] font-bold uppercase tracking-wider rounded-lg transition-all cursor-pointer ${method === "manual" ? "text-[#5548E8] border-b-2 border-[#5548E8] rounded-none" : "text-slate-400 hover:text-slate-600"}`}
                  >
                    <Type size={14} />
                    Manual
                  </button>
                  <button
                    onClick={() => setMethod("structured")}
                    className={`flex items-center gap-2 px-3 py-1.5 text-[11px] font-bold uppercase tracking-wider rounded-lg transition-all cursor-pointer ${method === "structured" ? "text-[#5548E8] border-b-2 border-[#5548E8] rounded-none" : "text-slate-400 hover:text-slate-600"}`}
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
                        dragActive ? 'border-[#5548E8] bg-[#F0EFFF]' : 'border-slate-200 bg-white hover:border-[#5548E8] hover:bg-slate-50/50'
                      }`}
                      onDragEnter={() => setDragActive(true)}
                      onDragLeave={() => setDragActive(false)}
                      onDrop={handleVisionDrop}
                      onDragOver={(e) => e.preventDefault()}
                    >
                      <div className="w-20 h-20 bg-slate-50 text-slate-400 rounded-3xl flex items-center justify-center mb-6 group-hover:bg-[#F0EFFF] group-hover:text-[#5548E8] transition-all shadow-inner">
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
                            <div className="w-10 h-10 rounded-xl bg-[#F0EFFF] text-[#5548E8] border border-[#D9D5FB] flex items-center justify-center shrink-0">
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
                          <span className="text-[10px] font-bold text-[#463AD4] uppercase tracking-wider bg-[#F0EFFF] border border-[#D9D5FB] rounded-full px-2.5 py-1">
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
                          <div
                            role="alert"
                            className="border border-red-200 bg-red-50 rounded-xl p-3 flex flex-col gap-3"
                          >
                            <div className="flex items-start gap-2">
                              <AlertCircle size={16} className="text-red-600 shrink-0 mt-0.5" />
                              <div className="min-w-0">
                                <p className="text-xs font-bold text-red-700">
                                  {extractionError.message}
                                </p>
                                {extractionError.requestId && (
                                  <p className="text-[11px] font-semibold text-red-600 tabular-nums mt-1">
                                    Reference ID: {extractionError.requestId}
                                  </p>
                                )}
                              </div>
                            </div>
                            <button
                              type="button"
                              onClick={() => setMethod("structured")}
                              className="self-start px-3 py-1.5 bg-white border border-red-200 text-red-700 rounded-lg text-[11px] font-bold uppercase tracking-wider hover:bg-red-100 transition-colors cursor-pointer"
                            >
                              Use Form Entry
                            </button>
                          </div>
                        )}
                      </div>
                    )}

                    <div className="bg-[#F0EFFF] border border-[#D9D5FB] rounded-2xl p-4 flex items-start gap-3">
                      <AlertCircle size={16} className="text-[#5548E8] shrink-0 mt-0.5" />
                      <p className="text-[11px] text-[#463AD4] font-semibold leading-relaxed">
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
                    <label htmlFor="manual-prescription-text" className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">
                      Pasted Prescription Text
                    </label>
                    <textarea
                      id="manual-prescription-text"
                      placeholder="Paste prescription text, clinical notes, or regimen details here..."
                      value={manualText}
                      onChange={(event) => setManualText(event.target.value)}
                      className="flex-1 w-full p-8 bg-white border border-slate-200 rounded-3xl text-slate-700 focus:outline-none focus:ring-4 focus:ring-[#D9D5FB] focus:border-[#5548E8] transition-all resize-none shadow-inner font-mono text-base leading-relaxed"
                    />
                    <button
                      type="button"
                      onClick={handleManualExtraction}
                      className="py-3 bg-[#5548E8] text-white rounded-lg font-bold hover:bg-[#463AD4] transition-all cursor-pointer text-[11px] uppercase tracking-wider"
                    >
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
                        className="px-3 py-1.5 bg-[#F0EFFF] text-[#5548E8] rounded-lg text-xs font-bold flex items-center gap-2 hover:bg-[#5548E8] hover:text-white transition-all shadow-sm cursor-pointer"
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
                                data-extraction-origin={extractedFields.has(medicationFieldKey(med.id, "name")) ? "vision" : undefined}
                                data-extraction-confidence={lowConfidenceAttribute(lowConfidenceFields, medicationFieldKey(med.id, "name"))}
                                title={lowConfidenceTitle(lowConfidenceFields, medicationFieldKey(med.id, "name"))}
                                className={`w-full px-4 py-2.5 border rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-[#D9D5FB] focus:border-[#5548E8] transition-all ${extractionFieldClass(extractedFields, lowConfidenceFields, medicationFieldKey(med.id, "name"), "bg-slate-50 border-slate-200")}`}
                                value={med.name}
                                onChange={(e) => updateMedication(med.id, { name: e.target.value })}
                              />
                            </div>
                            <div className="flex flex-col gap-1.5">
                              <label className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Dosage Strength</label>
                              <input
                                placeholder="e.g. 500mg"
                                data-extraction-origin={extractedFields.has(medicationFieldKey(med.id, "dosage")) ? "vision" : undefined}
                                data-extraction-confidence={lowConfidenceAttribute(lowConfidenceFields, medicationFieldKey(med.id, "dosage"))}
                                title={lowConfidenceTitle(lowConfidenceFields, medicationFieldKey(med.id, "dosage"))}
                                className={`w-full px-4 py-2.5 border rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-[#D9D5FB] focus:border-[#5548E8] transition-all ${extractionFieldClass(extractedFields, lowConfidenceFields, medicationFieldKey(med.id, "dosage"), "bg-slate-50 border-slate-200")}`}
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
                                data-extraction-origin={extractedFields.has(medicationFieldKey(med.id, "frequency")) ? "vision" : undefined}
                                data-extraction-confidence={lowConfidenceAttribute(lowConfidenceFields, medicationFieldKey(med.id, "frequency"))}
                                title={lowConfidenceTitle(lowConfidenceFields, medicationFieldKey(med.id, "frequency"))}
                                className={`w-full px-4 py-2.5 border rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-[#D9D5FB] focus:border-[#5548E8] transition-all ${extractionFieldClass(extractedFields, lowConfidenceFields, medicationFieldKey(med.id, "frequency"), "bg-slate-50 border-slate-200")}`}
                                value={med.frequency}
                                onChange={(e) => updateMedication(med.id, { frequency: e.target.value })}
                              />
                            </div>
                            <div className="flex flex-col gap-1.5">
                              <label className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Duration</label>
                              <input
                                placeholder="e.g. 10 days"
                                data-extraction-origin={extractedFields.has(medicationFieldKey(med.id, "duration")) ? "vision" : undefined}
                                data-extraction-confidence={lowConfidenceAttribute(lowConfidenceFields, medicationFieldKey(med.id, "duration"))}
                                title={lowConfidenceTitle(lowConfidenceFields, medicationFieldKey(med.id, "duration"))}
                                className={`w-full px-4 py-2.5 border rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-[#D9D5FB] focus:border-[#5548E8] transition-all ${extractionFieldClass(extractedFields, lowConfidenceFields, medicationFieldKey(med.id, "duration"), "bg-slate-50 border-slate-200")}`}
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
                      className="w-full py-3 border-2 border-dashed border-slate-200 hover:border-[#5548E8] hover:bg-[#F0EFFF] text-slate-500 hover:text-[#463AD4] rounded-2xl text-xs font-bold uppercase tracking-wider flex items-center justify-center gap-2 transition-all cursor-pointer"
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
                {extractionWarnings.length > 0 && (
                  <div className="bg-amber-50 border border-amber-200 rounded-xl p-3 flex items-start gap-3">
                    <AlertCircle size={16} className="text-amber-600 mt-0.5 shrink-0" />
                    <div className="space-y-2">
                      <p className="text-[11px] font-bold text-amber-800 uppercase tracking-wider">
                        Extraction warnings
                      </p>
                      <ul className="space-y-1">
                        {extractionWarnings.map((warning, index) => (
                          <li key={`${warning}-${index}`} className="text-xs text-amber-900 leading-relaxed font-medium">
                            {warning}
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>
                )}

                {medications.map((med, i) => (
                  <div key={med.id} className="p-4 bg-slate-50 border border-slate-200 rounded-2xl space-y-3 relative group transition-all hover:bg-white hover:border-[#D9D5FB]">
                    <div className="flex justify-between items-center border-b border-slate-100 pb-2 mb-2">
                      <span className="text-[10px] font-bold text-[#5548E8] uppercase tracking-wider">Medication #{i+1}</span>
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
                      <button className="text-slate-300 hover:text-[#5548E8] transition-colors cursor-pointer">
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
                  <label htmlFor="treatment-start-at" className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">
                    Treatment Starts
                  </label>
                  <input
                    id="treatment-start-at"
                    type="datetime-local"
                    value={treatmentStartAt}
                    onChange={(e) => setTreatmentStartAt(e.target.value)}
                    className="w-full px-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-[#D9D5FB] focus:border-[#5548E8] transition-all"
                  />
                  <p className="text-[11px] text-slate-500 px-1">
                    Used to anchor planned reminders and follow-up timing once monitoring starts.
                  </p>
                </div>

                <div className="flex flex-col gap-1.5 mt-4">
                  <label htmlFor="clinical-objective" className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">
                    Treatment Objective <span className="text-slate-400 normal-case font-medium tracking-normal">— what the agent should focus on</span>
                  </label>
                  <textarea
                    id="clinical-objective"
                    required
                    value={clinicalObjective}
                    onChange={(e) => {
                      setClinicalObjective(e.target.value);
                      clearExtractedField("treatment.clinical_objective");
                    }}
                    placeholder="e.g. Monitor for ACE-inhibitor cough and dizziness on standing. Confirm the patient takes the morning dose with food."
                    data-extraction-origin={extractedFields.has("treatment.clinical_objective") ? "vision" : undefined}
                    data-extraction-confidence={lowConfidenceAttribute(lowConfidenceFields, "treatment.clinical_objective")}
                    title={lowConfidenceTitle(lowConfidenceFields, "treatment.clinical_objective")}
                    className={`w-full pl-4 pr-10 py-3 border rounded-xl text-sm min-h-[80px] focus:outline-none focus:ring-2 focus:ring-[#D9D5FB] focus:border-[#5548E8] transition-all resize-none ${extractionFieldClass(extractedFields, lowConfidenceFields, "treatment.clinical_objective", "bg-slate-50 border-slate-200")}`}
                  />
                  <p className="text-[11px] text-slate-500 px-1">
                    Used to focus the agent's check-in questions throughout the treatment cycle.
                  </p>
                </div>

                <div className="bg-slate-50 border border-slate-200 rounded-xl p-3 flex items-start gap-3">
                  <AlertCircle size={16} className="text-slate-400 mt-0.5 shrink-0" />
                  <p className="text-xs text-slate-500 leading-relaxed font-medium italic">
                    RxNorm grounding and interaction checks will run when the agent activates this treatment.
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
          patient={{
            name: patientName,
            dob: patientDob,
            mrn: patientMrn,
            phone: patientPhone,
            allergies: currentPatientAllergies,
          }}
          treatmentStartAt={treatmentStartAt}
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

function treatmentCreatedDescription(result: {
  treatment_id: string;
  patient_id: string;
  analysis_id: string | null;
}): string {
  const treatment = `Treatment ID: ${result.treatment_id.slice(0, 8)}…`;
  const patient = `Patient ID: ${result.patient_id.slice(0, 8)}…`;
  const analysis = result.analysis_id
    ? `Analysis ID: ${result.analysis_id.slice(0, 8)}…`
    : "Analysis pending";
  return `${treatment} · ${patient} · ${analysis}`;
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

// Manual paste is intentionally conservative: it only drafts obvious
// medication rows, then pushes the pharmacist back into the reviewed form.
function parseManualMedicationText(value: string): Medication[] {
  return value
    .split(/\n|;/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map(parseManualMedicationLine)
    .filter((medication): medication is Medication => medication !== null);
}

function parseManualMedicationLine(line: string): Medication | null {
  const normalized = line.replace(/^\s*(?:[-*]|\d+[.)])\s*/, "").trim();
  const dosage = firstMatch(normalized, /\b\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml|iu|units?|tabs?|tablets?|caps?|capsules?)\b/i);
  const frequency = firstFrequencyMatch(normalized);
  const duration = firstMatch(normalized, /\b(?:for|x)\s+(\d+\s*(?:days?|weeks?|months?))\b/i);
  const name = cleanedMedicationName(normalized, [dosage, frequency, duration]);

  if (!name) {
    return null;
  }

  return {
    id: crypto.randomUUID(),
    name,
    dosage: dosage ?? "",
    frequency: frequency ?? "",
    duration: duration ?? "",
  };
}

function firstFrequencyMatch(value: string): string | null {
  const patterns = [
    /\b(?:once|twice|three times|four times)\s+daily\b/i,
    /\bevery\s+\d+\s+hours?\b/i,
    /\b(?:qd|od|bid|tid|qid|qhs|q4h|q6h|q8h|q12h|prn)\b/i,
    /\bas needed\b/i,
  ];
  for (const pattern of patterns) {
    const match = firstMatch(value, pattern);
    if (match) return match;
  }
  return null;
}

function firstMatch(value: string, pattern: RegExp): string | null {
  const match = value.match(pattern);
  if (!match) {
    return null;
  }
  return (match[1] ?? match[0]).trim();
}

function cleanedMedicationName(value: string, parts: Array<string | null>): string {
  let name = value;
  for (const part of parts) {
    if (part) {
      name = name.replace(part, " ");
    }
  }
  return name
    .replace(/\b(?:for|x|po|by mouth|take|tablet|capsule|daily)\b/gi, " ")
    .replace(/\s+/g, " ")
    .replace(/[,.:/-]+$/g, "")
    .trim();
}

function extractedFieldKeys(
  prescription: ExtractedPrescription,
  medicationDrafts: Medication[],
): Set<ExtractionFieldKey> {
  const keys = new Set<ExtractionFieldKey>();
  addIfPresent(keys, "patient.name", prescription.patient.name);
  addIfPresent(keys, "patient.dob", prescription.patient.dob);
  addIfPresent(keys, "patient.mrn", prescription.patient.mrn);
  addIfPresent(keys, "patient.phone", prescription.patient.phone);
  addIfPresent(
    keys,
    "treatment.clinical_objective",
    prescription.treatment.clinical_objective,
  );

  prescription.medications.forEach((medication, index) => {
    const draft = medicationDrafts[index];
    if (!draft) {
      return;
    }
    addIfPresent(keys, medicationFieldKey(draft.id, "name"), medication.name);
    addIfPresent(keys, medicationFieldKey(draft.id, "dosage"), medication.dosage);
    addIfPresent(keys, medicationFieldKey(draft.id, "frequency"), medication.frequency);
    addIfPresent(keys, medicationFieldKey(draft.id, "duration"), medication.duration);
  });

  return keys;
}

function lowConfidenceFieldKeys(
  prescription: ExtractedPrescription,
  medicationDrafts: Medication[],
): Set<ExtractionFieldKey> {
  const keys = new Set<ExtractionFieldKey>();
  addIfLowConfidence(keys, "patient.name", prescription.patient.confidence.name);
  addIfLowConfidence(keys, "patient.dob", prescription.patient.confidence.dob);
  addIfLowConfidence(keys, "patient.mrn", prescription.patient.confidence.mrn);
  addIfLowConfidence(keys, "patient.phone", prescription.patient.confidence.phone);
  addIfLowConfidence(
    keys,
    "treatment.clinical_objective",
    prescription.treatment.confidence.clinical_objective,
  );

  prescription.medications.forEach((medication, index) => {
    const draft = medicationDrafts[index];
    if (!draft) {
      return;
    }
    addIfLowConfidence(keys, medicationFieldKey(draft.id, "name"), medication.confidence.name);
    addIfLowConfidence(keys, medicationFieldKey(draft.id, "dosage"), medication.confidence.dosage);
    addIfLowConfidence(
      keys,
      medicationFieldKey(draft.id, "frequency"),
      medication.confidence.frequency,
    );
    addIfLowConfidence(
      keys,
      medicationFieldKey(draft.id, "duration"),
      medication.confidence.duration,
    );
  });

  return keys;
}

function addIfPresent(keys: Set<ExtractionFieldKey>, key: ExtractionFieldKey, value: string | null) {
  if (value !== null && value.trim() !== "") {
    keys.add(key);
  }
}

function addIfLowConfidence(
  keys: Set<ExtractionFieldKey>,
  key: ExtractionFieldKey,
  confidence: number | null | undefined,
) {
  if (confidence !== null && confidence !== undefined && confidence < LOW_CONFIDENCE_THRESHOLD) {
    keys.add(key);
  }
}

function medicationFieldKey(id: string, field: keyof Medication): ExtractionFieldKey {
  return `medication.${id}.${field}`;
}

function extractionFieldClass(
  extractedFields: Set<ExtractionFieldKey>,
  lowConfidenceFields: Set<ExtractionFieldKey>,
  key: ExtractionFieldKey,
  fallback: string,
) {
  if (lowConfidenceFields.has(key)) {
    return lowConfidenceFieldClass;
  }
  if (extractedFields.has(key)) {
    return extractedFieldClass;
  }
  return fallback;
}

function lowConfidenceAttribute(
  lowConfidenceFields: Set<ExtractionFieldKey>,
  key: ExtractionFieldKey,
) {
  return lowConfidenceFields.has(key) ? "low" : undefined;
}

function lowConfidenceTitle(
  lowConfidenceFields: Set<ExtractionFieldKey>,
  key: ExtractionFieldKey,
) {
  return lowConfidenceFields.has(key) ? LOW_CONFIDENCE_TITLE : undefined;
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

function appendPatientAllergies(existing: string[], draft: string): string[] {
  const seen = new Set(existing.map((allergy) => allergy.toLocaleLowerCase()));
  const additions = parsePatientAllergyDraft(draft).filter((allergy) => {
    const key = allergy.toLocaleLowerCase();
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
  return [...existing, ...additions];
}

function parsePatientAllergyDraft(value: string): string[] {
  // Match the backend contract: submit structured entries, never blank strings.
  return value
    .split(/[,\n]/)
    .map((allergy) => allergy.trim())
    .filter(Boolean);
}

function toTreatmentStartIso(value: string): string | null {
  if (!value) {
    return null;
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
}

function formatTreatmentStartDraft(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

interface ConfirmTreatmentModalProps {
  patient: { name: string; dob: string; mrn: string; phone: string; allergies: string[] };
  treatmentStartAt: string;
  objective: string;
  medications: Medication[];
  onCancel: () => void;
  onConfirm: () => void;
  submitting: boolean;
}

function ConfirmTreatmentModal({
  patient, treatmentStartAt, objective, medications, onCancel, onConfirm, submitting,
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
            <div className="mt-3 bg-slate-50 border border-slate-100 rounded-xl p-4">
              <div className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2">
                Known Allergies
              </div>
              {patient.allergies.length > 0 ? (
                <div className="flex flex-wrap gap-2">
                  {patient.allergies.map((allergy) => (
                    <span
                      key={allergy}
                      className="rounded-full border border-red-200 bg-red-50 px-2.5 py-1 text-[11px] font-bold text-red-700"
                    >
                      {allergy}
                    </span>
                  ))}
                </div>
              ) : (
                <p className="text-xs font-semibold text-slate-500">No allergies recorded.</p>
              )}
            </div>
          </section>

          <section>
            <h3 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-3">Treatment Timeline</h3>
            <div className="bg-slate-50 border border-slate-100 rounded-xl p-4 text-sm">
              <span className="text-slate-500">Starts:</span>{" "}
              <span className="font-semibold text-slate-900 tabular-nums">
                {treatmentStartAt ? formatTreatmentStartDraft(treatmentStartAt) : "Not set"}
              </span>
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
                      <span className="text-[10px] font-bold text-[#5548E8] uppercase tracking-wider">#{i + 1}</span>
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
