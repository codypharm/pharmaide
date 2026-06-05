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

```mermaid
flowchart LR
  Pharmacist[Pharmacist Web App<br/>React + Vite] --> API[FastAPI Backend]

  Patient[Patient on WhatsApp] --> Meta[Meta WhatsApp Cloud API]
  Meta --> Webhook[Webhook<br/>/webhooks/whatsapp]
  Webhook --> API

  API --> Auth[Auth Layer<br/>Dev Header / GCIP]
  API --> DB[(Postgres / CockroachDB<br/>relational data + vectors)]
  API --> Files[Knowledge File Storage<br/>local or GCS]
  API --> Tasks[Task Runner<br/>in-process or Cloud Tasks]

  Tasks --> Workers[Internal Worker Routes]
  Workers --> DB

  API --> OpenAI[OpenAI + PydanticAI<br/>typed agents and embeddings]
  API --> RxNorm[RxNorm / RxNav<br/>drug name grounding]
  API --> DailyMed[DailyMed<br/>public label evidence cache]
  API --> Safety[Safety Provider<br/>model fallback now<br/>remote Llama Guard + AgentDoG later]

  DB --> Audit[Audit Trail<br/>metadata-only clinical and operational events]
```

PharmaAide is intentionally split into thin HTTP routes, workflow services,
provider adapters, and typed agent modules. Routes translate requests,
services own workflow state, providers isolate external systems, and all
patient-facing AI decisions pass through validated Pydantic schemas.

```mermaid
flowchart TB
  Routes[app/api<br/>HTTP boundary]
  Auth[app/auth.py<br/>actor and workspace scope]
  Services[app/services<br/>business workflows]
  Agents[app/agents<br/>LLM, graph, safety nodes]
  Providers[Provider adapters<br/>OpenAI, RxNorm, DailyMed,<br/>WhatsApp, Safety Gateway]
  Models[app/db/models.py<br/>persistence schema]
  Schemas[app/api/schemas.py<br/>request and response contracts]
  Tests[tests + evaluations<br/>release gates]

  Routes --> Auth
  Routes --> Schemas
  Routes --> Services
  Services --> Models
  Services --> Agents
  Services --> Providers
  Agents --> Providers
  Tests --> Routes
  Tests --> Services
  Tests --> Agents
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

## Main Flow: Treatment Analysis

Treatment analysis starts when a pharmacist creates or reruns a treatment
analysis. The graph produces pharmacist-facing clinical reasoning, relative
schedule previews, medication groundings, safety notes, and traceable audit
events. Model-backed review is kept separate from licensed DDI truth so the app
does not present speculative model output as provider-confirmed interactions.

```mermaid
sequenceDiagram
  participant UI as Frontend
  participant API as FastAPI /treatments
  participant DB as Database
  participant Task as Task Runner
  participant Graph as Analysis Graph
  participant Rx as RxNorm
  participant DM as DailyMed
  participant KB as Knowledge Retrieval
  participant LLM as PydanticAI/OpenAI

  UI->>API: POST /treatments or rerun analysis
  API->>DB: create or supersede treatment analysis row
  API->>DB: audit treatment creation or analysis request
  API->>Task: schedule analysis worker
  API-->>UI: analysis_id + pending status

  Task->>Graph: run graph for treatment
  Graph->>DB: load patient, treatment, medications, objective
  Graph->>Rx: normalize medication names and RxCUIs
  Graph->>DM: fetch/cache public drug label context
  Graph->>KB: retrieve clinic knowledge and DailyMed snippets
  Graph->>LLM: create typed clinical reasoning
  Graph->>Graph: generate schedule from validated medication instructions
  Graph->>DB: save completed/failed analysis result
  Graph->>DB: audit outcome
  UI->>API: GET /treatments/{id}/analysis
  API-->>UI: summary, red flags, groundings, schedule preview
```

```mermaid
flowchart LR
  Pending[Pending analysis row]
  Load[Load treatment state]
  Ground[Ground medications<br/>RxNorm]
  Interactions[Interaction boundary<br/>licensed provider later]
  Daily[DailyMed context/cache]
  Retrieve[Clinic KB retrieval<br/>plus reranking]
  Schedule[Schedule grammar]
  Review[Clinical safety review]
  Summary[Typed summary output]
  Save[Persist result + audit]

  Pending --> Load --> Ground --> Interactions --> Daily --> Retrieve --> Schedule --> Review --> Summary --> Save
```

## Main Flow: WhatsApp Care Loop

The WhatsApp flow keeps the pharmacist in control. Incoming patient messages are
verified, deduplicated, routed to the active treatment for that workspace, and
buffered before the system generates one conversational turn. Replies that are
unsafe, uncertain, or outside the assistant boundary are held for pharmacist
triage instead of being sent automatically.

```mermaid
sequenceDiagram
  participant Patient as Patient WhatsApp
  participant Meta as WhatsApp Cloud API
  participant Webhook as /webhooks/whatsapp
  participant Buffer as Message Buffer
  participant Worker as Patient Message Worker
  participant Reply as Reply Agent
  participant Safety as Safety Sandwich
  participant Triage as Pharmacist Triage
  participant Delivery as Delivery Worker
  participant DB as Database
  participant UI as Surveillance/Triage UI

  Patient->>Meta: send message
  Meta->>Webhook: signed webhook event
  Webhook->>Webhook: verify signature
  Webhook->>DB: find active treatment by phone + workspace
  Webhook->>DB: dedupe provider message id
  Webhook->>Buffer: store inbound message
  Webhook->>Worker: schedule buffered turn

  Worker->>Buffer: aggregate recent unprocessed messages
  Worker->>Reply: classify intent and draft response
  Reply->>DB: load treatment context, schedule, updates, evidence
  Reply->>Safety: input guard + clinical referee + output guard

  alt safe to send
    Safety-->>Worker: send
    Worker->>DB: save queued outbound message
    Delivery->>Meta: send WhatsApp message
    Delivery->>DB: mark sent or failed
  else needs pharmacist
    Safety-->>Worker: hold_for_pharmacist
    Worker->>DB: save held draft
    Worker->>Triage: create triage item
    UI->>Triage: pharmacist reviews
    Triage->>DB: approve or reject held draft
    Triage->>DB: queue approved draft for delivery
    Delivery->>Meta: send queued message
  end
```

```mermaid
flowchart TB
  Webhooks[webhooks.py<br/>Meta verification and event parsing]
  Routing[whatsapp_webhook.py<br/>phone/workspace active-treatment routing]
  Buffer[patient_message_buffer.py<br/>dedupe, store, debounce]
  Worker[patient_message_worker.py<br/>process buffered turn]
  Classifier[patient_reply_classifier.py<br/>intent classification]
  Reply[patient_reply_service.py<br/>draft patient response]
  Safety[patient_safety.py<br/>safety sandwich]
  Triage[triage_items.py<br/>human review queue]
  Delivery[message_delivery.py<br/>queued, sent, failed]
  Audit[safety_audit + audit logs]

  Webhooks --> Routing --> Buffer --> Worker
  Worker --> Classifier --> Reply --> Safety
  Safety -->|safe| Delivery
  Safety -->|hold| Triage
  Delivery --> Audit
  Triage --> Audit
```

## Core Data Model

The diagram below shows persisted tables. Course completion reports are computed
from treatment, adherence, patient update, and triage rows rather than stored in
a separate report table. Monitoring cycle state is represented on the treatment
row through status, automation mode, and chat response mode.

```mermaid
flowchart LR
  Patient[Patient] --> Treatment[Treatment]
  Treatment --> Meds[Medications]
  Treatment --> Analyses[Treatment Analyses]
  Treatment --> Messages[Conversation Messages]
  Treatment --> Triage[Triage Items]
  Treatment --> Adherence[Adherence Events]
  Treatment --> Checkins[Check-ins]
  Treatment --> State[Treatment status<br/>automation mode<br/>chat response mode]

  Knowledge[Knowledge Documents] --> Chunks[Knowledge Chunks + Embeddings]
  Audit[Audit Logs] --> Patient
  Audit --> Treatment
  Audit --> Messages
```

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
uv run python scripts/gcip_claims_manifest.py <claims-manifest.json>
uv run python scripts/retention_approval_manifest.py <retention-manifest.json>
uv run python scripts/cloud_tasks_scheduler_manifest.py <cloud-tasks-manifest.json>
uv run python scripts/knowledge_storage_manifest.py <knowledge-storage-manifest.json>
uv run python scripts/evaluation_release_gate.py
uv run python scripts/production_preflight.py
uv run python scripts/deployment_manifest.py <deployment-manifest.json>
uv run python scripts/knowledge_storage_smoke.py
uv run python scripts/safety_gateway_manifest.py <safety-gateway-manifest.json>
uv run python scripts/safety_gateway_smoke.py
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
