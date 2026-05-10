// Tiny typed fetch wrapper. Keeps base-URL handling, JSON encode/decode,
// and X-Request-ID propagation in one place so route modules stay focused
// on their endpoint contract.

const DEFAULT_BASE_URL = "http://localhost:8000";

function baseUrl(): string {
  // Vite exposes import.meta.env at build time. Fall back to the local
  // backend so first-clone dev works without a .env file.
  return import.meta.env.VITE_API_BASE_URL ?? DEFAULT_BASE_URL;
}

export type ValidationFieldError = {
  loc: (string | number)[];
  msg: string;
  type: string;
};

export class ApiError extends Error {
  status: number;
  requestId: string | null;
  body: unknown;

  constructor(status: number, requestId: string | null, body: unknown, message: string) {
    super(message);
    this.status = status;
    this.requestId = requestId;
    this.body = body;
  }
}

export class ValidationError extends ApiError {
  fieldErrors: ValidationFieldError[];

  constructor(requestId: string | null, fieldErrors: ValidationFieldError[]) {
    super(422, requestId, { detail: fieldErrors }, "validation_failed");
    this.fieldErrors = fieldErrors;
  }
}

export class ConflictError extends ApiError {
  errorCode: string;

  constructor(requestId: string | null, body: unknown, errorCode: string) {
    super(409, requestId, body, errorCode);
    this.errorCode = errorCode;
  }
}

export async function postJson<TRequest, TResponse>(
  path: string,
  body: TRequest,
): Promise<TResponse> {
  const response = await fetch(`${baseUrl()}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  const requestId = response.headers.get("X-Request-ID");
  const text = await response.text();
  const parsed: unknown = text ? JSON.parse(text) : null;

  if (response.ok) {
    return parsed as TResponse;
  }

  if (response.status === 422 && isPydanticErrorBody(parsed)) {
    throw new ValidationError(requestId, parsed.detail);
  }

  if (response.status === 409 && isErrorEnvelope(parsed)) {
    throw new ConflictError(requestId, parsed, parsed.detail.error);
  }

  throw new ApiError(
    response.status,
    requestId,
    parsed,
    `Request failed: ${response.status}`,
  );
}

function isPydanticErrorBody(body: unknown): body is { detail: ValidationFieldError[] } {
  return (
    typeof body === "object" &&
    body !== null &&
    Array.isArray((body as { detail?: unknown }).detail)
  );
}

function isErrorEnvelope(body: unknown): body is { detail: { error: string } } {
  return (
    typeof body === "object" &&
    body !== null &&
    typeof (body as { detail?: { error?: unknown } }).detail === "object" &&
    typeof (body as { detail: { error?: unknown } }).detail.error === "string"
  );
}
