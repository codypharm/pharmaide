# PharmaAide

PharmaAide is a human-in-the-loop medication adherence and patient surveillance
system for pharmacists. It helps turn a treatment plan into monitored patient
support: treatment analysis, medication reminders, WhatsApp check-ins, AI-drafted
patient replies, pharmacist triage, knowledge-grounded evidence, and audit trails.

The product is designed around a simple rule: the AI can assist, but the
pharmacist stays in control.

## What It Does

PharmaAide supports a pharmacist workflow from treatment intake through active
monitoring:

- Create a patient treatment with medications, dosage, frequency, duration, and
  clinical objective.
- Analyze the treatment with a LangGraph/PydanticAI clinical workflow.
- Ground medications with RxNorm and generate a relative reminder schedule.
- Retrieve clinic-uploaded knowledge and DailyMed references for grounded
  analysis and patient interaction questions.
- Start an active monitoring cycle that queues WhatsApp reminders and check-ins.
- Buffer bursty inbound WhatsApp patient messages into a single conversational
  turn.
- Generate patient reply drafts with safety review before delivery.
- Route unsafe, uncertain, or pharmacist-required replies into a triage queue.
- Let pharmacists take over a patient conversation while automation continues
  scheduled reminders and check-ins.
- Track adherence events, patient-reported updates, treatment completion, and
  course reports.
- Audit operational and clinical workflow actions with metadata-only payloads.

## Product Highlights

PharmaAide combines a pharmacist dashboard, AI-assisted clinical workflows, and
WhatsApp patient engagement into one controlled workspace.

- **Clinical treatment analysis**: medication grounding, schedule generation,
  knowledge retrieval, safety review, and pharmacist-facing summary output.
- **Patient surveillance**: active treatment cycles, adherence signals,
  patient-reported updates, completion reports, and risk flags.
- **WhatsApp care loop**: outbound reminders, check-ins, delivery callbacks,
  signed webhooks, inbound buffering, and debounced patient replies.
- **Pharmacist triage**: AI-held drafts, review decisions, approval/cancel
  actions, manual pharmacist takeover, and visible conversation control.
- **Knowledge grounding**: clinic protocols, formularies, PDFs, CSVs, text
  files, DailyMed references, embeddings, balanced retrieval, and reranking.
- **Safety-first orchestration**: typed PydanticAI outputs, safety sandwich,
  remote safety-provider adapters, and pharmacist-in-the-loop escalation.
- **Workspace isolation**: GCIP/Firebase auth model, workspace claims, membership
  checks, scoped knowledge retrieval, and workspace-aware WhatsApp routing.
- **Operational traceability**: structured logs, metadata-only audit trail,
  internal worker routes, Cloud Tasks seams, and retention cleanup controls.

## Platform Stack

PharmaAide is built with production-grade healthcare workflow infrastructure in
mind:

- **Frontend**: Vite, React, React Router, Public Sans, vanilla CSS clinical UI.
- **Backend**: FastAPI, SQLAlchemy async, Alembic, Pydantic, PydanticAI.
- **AI orchestration**: LangGraph, OpenAI models, typed agent outputs, structured
  validators.
- **Retrieval**: OpenAI embeddings, pgvector-compatible vector search, reranking,
  clinic uploads, DailyMed cache.
- **Medication data**: RxNorm/RxNav grounding, DailyMed public label evidence,
  pluggable DDI-provider path for Lexicomp, DrugBank, or another approved source.
- **Messaging**: Meta WhatsApp Cloud API, signed webhooks, delivery status
  callbacks, patient-message buffering.
- **Auth and tenancy**: GCIP/Firebase ID tokens, workspace custom claims,
  membership claim checks.
- **Cloud target**: GCP Cloud Run, Cloud Tasks, Pub/Sub/Scheduler patterns,
  Secret Manager, service-to-service OIDC.
- **Safety providers**: in-app typed safety checks plus backend-only remote HTTP
  adapters for Llama Guard and AgentDoG.
- **Data layer**: Postgres/Cockroach-compatible schema, pgvector-compatible
  embeddings, metadata-oriented audit logs, archive-gated retention cleanup.

## Architecture

```text
React Dashboard
    |
    | HTTPS API calls with GCIP/Firebase identity
    v
FastAPI Backend
    |
    |-- Treatment and patient workflow services
    |-- LangGraph analysis graph
    |-- PydanticAI typed agents and validators
    |-- Safety sandwich: input guard -> clinical referee -> output guard
    |-- Knowledge retrieval over clinic uploads and DailyMed cache
    |-- WhatsApp webhook and message delivery services
    |-- Cloud Tasks/internal worker seams
    v
Postgres/Cockroach-compatible database with pgvector-compatible embeddings
```

Frontend:

- Vite + React
- React Router dashboard
- Public Sans clinical UI
- Memory-only Firebase/GCIP session persistence
- No PHI stored in localStorage or browser durable storage

Backend:

- FastAPI
- SQLAlchemy async + Alembic
- LangGraph
- PydanticAI
- OpenAI agents and embeddings
- RxNorm/RxNav medication grounding
- DailyMed knowledge cache
- Meta WhatsApp Cloud API
- Google Cloud Tasks adapter
- Structlog request-scoped logging

## Safety Model

PharmaAide is built as a pharmacist-controlled assistant, not an autonomous
clinical decision maker.

Key safety boundaries:

- AI outputs that touch patient data or medication logic are typed and validated
  with Pydantic models.
- Patient replies pass through a safety pipeline before delivery.
- Drafts that need human review are held and shown in triage.
- Pharmacists can approve, cancel, or manually respond.
- Pharmacist takeover stops free-text AI replies but keeps scheduled automation
  running.
- Audit payloads avoid patient message text, assistant drafts, medication names,
  dose text, and knowledge excerpts.
- Internal worker routes support Google-issued OIDC service identity.

The safety layer is designed to run as a backend-only gateway with Llama Guard
and AgentDoG, while retaining typed in-app safety checks for controlled
environments.

## Knowledge Grounding

The knowledge system supports:

- PDF, CSV, and text uploads.
- CSV row-aware segmentation that preserves column context.
- Recursive boundary-aware chunking with token windows.
- OpenAI embeddings.
- Balanced retrieval between clinic-uploaded content and global DailyMed data.
- Reranking before citations are passed to analysis/reply flows.
- Source-file deletion for user-uploaded assets in the current local storage
  adapter.

DailyMed data is cached globally because it is public reference data. Clinic
uploads remain workspace-scoped.

## Local Development

### Prerequisites

- Python 3.13
- `uv`
- Node.js
- Docker

### Backend

```bash
cd backend
cp .env.example .env
docker compose up -d
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
```

The backend runs at:

```text
http://127.0.0.1:8000
```

Health check:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/health/ready
```

### Frontend

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

The frontend usually runs at:

```text
http://localhost:5173
```

## Important Environment Variables

Backend variables live in `backend/.env.example`.

Common local values:

```env
PHARMAIDE_DATABASE_URL=postgresql+asyncpg://pharmaide:pharmaide@localhost:5432/pharmaide
PHARMAIDE_AUTH_MODE=disabled
PHARMAIDE_CORS_ALLOWED_ORIGINS=http://localhost:5173
PHARMAIDE_OPENAI_API_KEY=
PHARMAIDE_WHATSAPP_DELIVERY_PROVIDER=placeholder
PHARMAIDE_TASK_BACKEND=in_process
PHARMAIDE_SAFETY_PROVIDER=model
```

Deployment values are documented in `backend/.env.example` and
`frontend/.env.example`.

Frontend variables live in `frontend/.env.example`.

## Testing

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

Optional live evaluation tests are gated by environment variables so normal test
runs do not call external AI services:

```bash
cd backend
uv run python scripts/evaluation_release_gate.py
PHARMAIDE_RUN_LIVE_RAG_EVAL=1 uv run pytest tests/evaluations/test_live_rag_products_eval.py -q
PHARMAIDE_RUN_LIVE_LLM=1 PHARMAIDE_OPENAI_API_KEY=... uv run pytest tests/test_analysis_graph.py -q
```

## Main Product Screens

- Landing page
- Triage queue
- Patient surveillance
- Treatment detail
- New treatment
- Adherence heatmaps
- Clinical knowledge assets
- Knowledge ingestion status
- System audits
- Pharmacist profile

## Key Docs

- `docs/safety-provider-gateway.md`
- `ui-guide/clinical_command/DESIGN.md`

## Compliance Posture

PharmaAide is designed for HIPAA-adjacent, safety-first clinical operations.

- No frontend durable PHI storage.
- Metadata-only audit trail policy.
- Workspace-scoped access model.
- Signed WhatsApp webhook support.
- Internal worker auth support.
- Archive-gated retention cleanup support.

## License

No license has been declared yet.
