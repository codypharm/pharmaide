# Security Policy

PharmaAide is designed for HIPAA-adjacent clinical workflow exploration, but this
repository must not contain real patient data, production secrets, or private
clinical records.

## Reporting Security Issues

Please do not open a public issue for sensitive security findings.

If you find a vulnerability, contact the maintainer privately with:

- affected component or route
- reproduction steps
- impact
- suggested mitigation, if known

The maintainer will acknowledge the report and coordinate a fix before public
disclosure.

## Data Handling Rules

- Do not commit PHI, patient messages, prescription photos, real phone numbers,
  uploaded clinic documents, access tokens, API keys, or database URLs.
- Use `.env.example` for configuration shape only.
- Store real secrets in a local `.env` during development or a secret manager in
  deployment.
- Keep audit/log payloads metadata-only.
- Treat screenshots carefully. Mask patient names, phone numbers, message text,
  and identifiers before sharing.

## Dependency and Runtime Notes

- Backend dependencies are managed with `uv`.
- Frontend dependencies are managed with `npm`.
- Optional live tests may call external APIs and should stay opt-in through
  explicit environment variables.
- External safety gateway support exists as an adapter path; the low-cost demo
  configuration uses the in-app typed model safety provider.
