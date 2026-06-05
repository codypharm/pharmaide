# Contributing to PharmaAide

PharmaAide is a pharmacist-in-the-loop medication adherence project. Contributions
should preserve the core safety rule: AI may assist, but the pharmacist remains
in control.

## Development Setup

Backend:

```bash
cd backend
cp .env.example .env
docker compose up -d
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
```

Frontend:

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

## Pull Request Expectations

- Keep changes small and focused.
- Add or update tests for behavior changes.
- Do not commit secrets, PHI, local `.env` files, uploaded knowledge files, or
  generated runtime databases.
- Keep patient-facing AI output typed and validated with Pydantic/PydanticAI.
- Keep audit payloads metadata-only. Do not log patient messages, assistant
  drafts, medication names, dose details, or knowledge excerpts.
- Prefer existing modules and service boundaries over new abstractions.

## Checks

Backend:

```bash
cd backend
uv run ruff check app tests
uv run pytest
```

Frontend:

```bash
cd frontend
npm run build
npm run test
```

## Clinical Safety Boundaries

This project is not a replacement for professional clinical judgement. New
features that affect medication logic, patient messaging, adherence state,
triage, safety review, retrieval, or WhatsApp delivery should be reviewed with
extra care and covered by focused tests.
