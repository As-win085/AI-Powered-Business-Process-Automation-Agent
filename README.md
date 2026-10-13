# AI-Powered Business Process Automation Agent

A multi-tenant, full-stack AI business automation platform that processes invoices,
validates financial information, detects duplicates and unusual transactions, and
manages auditable approval workflows.

> Version 1.0 · October 2026 · Portfolio-focused · Multi-tenant · International-ready

The project demonstrates practical AI/ML engineering, backend architecture, database
design, security, testing and frontend development in one coherent, finishable
application. It is **not** an accounting system, a payment system, or a fraud detector.

---

## Why this project exists

A medium-sized company receives invoices from many suppliers. Finance staff open each
document, retype details, check arithmetic, compare against purchase orders, search for
duplicates, and chase approvals. This is repetitive, error-prone and slow.

This application acts as an intelligent **assistant** to the finance team. It automates
routine document handling and checks. **Authorized people remain responsible for
important financial approvals.**

### Core principle

> AI interprets documents; deterministic code enforces business rules; workflow
> automation moves records between states. An LLM never authorizes payments or bypasses
> approval controls.

---

## Scope at a glance

**In the MVP**

- Multi-tenant organizations with tenant-scoped users, suppliers, invoices and approvals
- Login, role-based access control and organization membership
- Secure PDF/image upload with private local file storage
- PDF text extraction and OCR for scanned documents
- LLM-based structured invoice extraction with schema validation
- Human review and correction of extracted fields
- Configurable deterministic invoice validation
- Exact and potential (fuzzy) duplicate detection
- Initial ML anomaly scoring with explainable signals
- Purchase-order matching
- Configurable approval workflow
- Background jobs, retry handling and job-status tracking
- Audit logs, notifications and an operational dashboard
- Automated tests, Docker-based local setup and deployment documentation

**Out of scope for the first release**

- Executing payments or moving money
- Replacing a full accounting or ERP system
- Claiming that AI can prove fraud
- Automatic approval of high-risk invoices
- Direct integration with live banks or enterprise accounting platforms
- Supporting every country's tax rules out of the box
- A production-grade cloud file-storage system in the first milestone

---

## Technology stack

| Layer | Decision |
| --- | --- |
| Backend | Python 3.11+, FastAPI, Pydantic v2 |
| ORM & migrations | SQLAlchemy 2.x, Alembic |
| Database | PostgreSQL |
| Frontend | React + TypeScript, Vite |
| API communication | REST / JSON, OpenAPI |
| PDF parsing | PyMuPDF |
| OCR | Tesseract (evaluate PaddleOCR later) |
| LLM | External API behind a provider interface |
| Data & ML | Pandas, NumPy, scikit-learn |
| Fuzzy matching | RapidFuzz |
| Background work | Celery + Redis |
| Tests | Pytest, HTTPX, frontend test tooling |
| Local environment | Docker Compose |
| File storage | Private local storage adapter (S3-compatible later) |
| Notifications | SMTP or transactional email provider |
| Version control | Git + GitHub |

Compatible dependency versions are pinned in the project files when the repository is
initialized.

---

## High-level architecture

```
React + TypeScript                FastAPI backend                  PostgreSQL
Tenant-aware dashboard  ───────►  Auth · Tenant context   ───────► Tenant-scoped records
Invoice review                    Permissions                     Audit history
Approvals                         Business services
                                  │
                                  ▼
                          Redis + Celery  ─────────────────────►  Processing pipeline
                          Async workers                            Local files → PDF/OCR
                          Retries · status                         → LLM provider → validation
                                                                    → duplicates → anomalies
```

| Component | Responsibility |
| --- | --- |
| React frontend | Upload documents, display extracted fields, show errors, review and approve |
| FastAPI backend | Authentication, permissions, upload endpoints, business rules, state transitions, APIs |
| PostgreSQL | Business records, processing status, extracted fields, approvals, audit events |
| Celery + Redis | Queue processing work, run workers outside the request/response cycle |
| Processing pipeline | Validation → text/OCR → LLM extraction → rules → duplicates → ML flags |
| Workflow engine | Route valid invoices to approvers, exceptions to review, notify, record decisions |

### Typical processing sequence

1. The frontend uploads a document to FastAPI.
2. The backend validates the file, stores metadata, and queues a job.
3. The API returns a document ID and processing status without waiting for OCR.
4. A worker extracts text and structured fields, then runs validation and ML checks.
5. Results are persisted in PostgreSQL and the dashboard reflects the current status.
6. Workers and the workflow handle retries safely, without duplicate side effects.

---

## Repository layout

```
ai-business-automation/
├── backend/
│   ├── app/
│   │   ├── api/           # auth, tenants, documents, invoices, approvals, analytics
│   │   ├── core/          # config, security, permissions, tenant_context
│   │   ├── db/            # session, models/
│   │   ├── schemas/       # Pydantic request/response schemas
│   │   ├── services/      # document, extraction, validation, duplicate, approval
│   │   ├── integrations/  # llm/, ocr/, storage/
│   │   ├── ml/            # features, train, predict, evaluate
│   │   ├── workers/       # Celery app and tasks
│   │   └── main.py
│   ├── migrations/        # Alembic
│   └── tests/
├── frontend/
│   └── src/               # components/, pages/, features/, services/, hooks/, types/
├── data/                  # synthetic/ demo data
├── docs/                  # requirements, architecture, database, security, api, roadmap
├── storage/               # local-only private files; never committed
├── docker-compose.yml
├── .env.example
├── .gitignore
└── README.md
```

---

## Quick start

> Implemented milestone by milestone. Current status: **Milestone 1 backend
> (foundation + tenant isolation)** complete and tested. See
> [`docs/roadmap.md`](docs/roadmap.md) for progress.

### Option A — Docker Compose (recommended)

```bash
# 1. Copy the environment template
cp .env.example .env

# 2. Start PostgreSQL, Redis, the API and the Celery worker
docker compose up -d --build db redis backend worker

# 3. Verify
curl http://localhost:8000/health

# 4. Seed demo data (two tenants, three users)
docker compose exec backend python -m scripts.seed
```

The backend runs `alembic upgrade head` automatically on start. Demo logins
(password `Password123!`): `admin@acme.com`, `finance@acme.com` (Acme) and
`admin@globex.com` (Globex).

The frontend is added in a later step and enabled with:

```bash
docker compose --profile frontend up
```

### Option B — Local backend

```bash
# 1. Environment + datastores
cp .env.example .env
docker compose up -d db redis          # PostgreSQL on :5432, Redis on :6379

# 2. Backend
cd backend
python -m venv .venv
#   Windows: .venv\Scripts\activate
#   macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
alembic upgrade head
python -m scripts.seed
uvicorn app.main:app --reload          # http://localhost:8000/docs
```

### Quality commands (from `backend/`)

```bash
ruff check .            # lint
ruff format .           # format
pytest                  # tests (needs PostgreSQL + the automation_test database)
```

> The test database `automation_test` is created automatically by
> `backend/docker/initdb/01-init.sql` on first database initialization.

---

## Documentation

| Document | Contents |
| --- | --- |
| [docs/requirements.md](docs/requirements.md) | Scope, functional requirements, acceptance criteria, state model, NFRs |
| [docs/architecture.md](docs/architecture.md) | Components, processing pipeline, tenant isolation, provider abstraction |
| [docs/database.md](docs/database.md) | Entity relationships, tables, constraints, migration strategy |
| [docs/security.md](docs/security.md) | Isolation, authentication, RBAC, storage controls, privacy, threat model |
| [docs/api.md](docs/api.md) | REST endpoint reference and authorization rules |
| [docs/roadmap.md](docs/roadmap.md) | Milestone-driven roadmap and 8-week mapping |

---

## Measuring success

| Metric | What it measures |
| --- | --- |
| Field-level extraction accuracy | Percentage of extracted fields matching ground truth |
| Duplicate precision / recall | Genuine flags vs. known duplicates found |
| Anomaly precision / recall | Performance on labeled test cases, where trustworthy labels exist |
| Processing latency | Elapsed time from upload to completed processing |
| Background-job success rate | Jobs completing successfully, including recovery after transient failures |
| Manual correction rate | Frequency of user corrections to extracted fields |
| Workflow completion rate | Share of documents reaching a valid final state |

Start with around 100–300 representative invoices: clean invoices, duplicates, missing
fields, calculation errors, varied layouts and deliberately unusual transactions. Use
synthetic or appropriately licensed data. **Report measured results only — never invent
accuracy or time-saving claims.**

---

## Definition of success for Milestone 1

Before any invoice-processing work begins, the following must all hold:

- The backend starts and connects to PostgreSQL.
- Database migrations create the expected tables.
- A user can authenticate.
- A user has a valid membership in a tenant.
- Tenant context is established by the backend.
- Requests without valid authentication are rejected.
- Cross-tenant reads and writes are denied.
- Automated tests run using documented commands.
- The frontend communicates with the backend.
- No secrets or private data are committed to Git.

---

## Portfolio quality expectations

The strongest evidence is a working end-to-end demo and **measured** engineering
results — not the number of technologies listed. This project documents:

- How tenant isolation works and how it is tested.
- How the extraction pipeline handles uncertainty.
- Why financial validation uses deterministic rules.
- How duplicate detection is evaluated.
- How anomaly detection is evaluated and where it can fail.
- How job retries avoid duplicate records.
- Which requirements are implemented and which remain future work.

---

## Contributing & working agreements

- Follow the folder structure above; add files only when their responsibility is needed.
- Keep business rules in services, never scattered across routes or UI components.
- Write tests alongside features; a milestone gate must pass before the next begins.
- Never commit `.env`, `storage/`, secrets, or private/sample real invoices.
