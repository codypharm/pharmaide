import { ApiError, postMultipart } from "./client";

type Confidence = number | null;

export type ExtractedPatient = {
  name: string | null;
  dob: string | null;
  mrn: string | null;
  phone: string | null;
  confidence: {
    name?: Confidence;
    dob?: Confidence;
    mrn?: Confidence;
    phone?: Confidence;
  };
};

export type ExtractedTreatment = {
  clinical_objective: string | null;
  confidence: {
    clinical_objective?: Confidence;
  };
};

export type ExtractedMedication = {
  name: string | null;
  dosage: string | null;
  frequency: string | null;
  duration: string | null;
  objective: string | null;
  confidence: {
    name?: Confidence;
    dosage?: Confidence;
    frequency?: Confidence;
    duration?: Confidence;
    objective?: Confidence;
  };
};

export type ExtractedPrescription = {
  patient: ExtractedPatient;
  treatment: ExtractedTreatment;
  medications: ExtractedMedication[];
  warnings: string[];
};

export class ExtractionError extends ApiError {
  errorCode: string;

  constructor(error: ApiError, errorCode: string) {
    super(error.status, error.requestId, error.body, errorCode);
    this.errorCode = errorCode;
  }
}

export async function extractPrescription(file: File): Promise<ExtractedPrescription> {
  const body = new FormData();
  body.append("file", file);
  try {
    return await postMultipart<ExtractedPrescription>("/prescriptions/extract", body);
  } catch (err) {
    if (err instanceof ApiError) {
      throw new ExtractionError(err, extractionErrorCode(err.body));
    }
    throw err;
  }
}

function extractionErrorCode(body: unknown): string {
  if (
    typeof body === "object" &&
    body !== null &&
    typeof (body as { detail?: { error?: unknown } }).detail === "object" &&
    typeof (body as { detail: { error?: unknown } }).detail.error === "string"
  ) {
    return (body as { detail: { error: string } }).detail.error;
  }
  return "extraction_failed";
}
