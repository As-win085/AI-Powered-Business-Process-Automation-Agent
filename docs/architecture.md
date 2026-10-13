# Architecture

> AI-Powered Business Process Automation Agent — Version 1.0 · October 2026

This document describes the system's structure, components, data flow and the key
architectural decisions. Requirements are defined in [`requirements.md`](requirements.md);
the data model in [`database.md`](database.md); security controls in
[`security.md`](security.md).

---

## 1. Architectural principles

1. **Multi-tenancy, data isolation and auditability are foundational**, not features
   bolted on later. Every layer enforces tenant boundaries.
2. **AI interprets; deterministic code decides.** LLMs extract and suggest, but business
   rules and state transitions are deterministic and server-side.
3. **Separation of concerns.** API routes are thin; business rules live in services.
4. **Provider independence.** The extraction pipeline depends on an interface, not a
   vendor.
5. **Async by default for slow work.** OCR/LLM/ML run in workers, never in a request.
6. **Everything important is an auditable event.**
7. **Local-first, cloud-ready.** Local storage and Docker Compose now; swappable adapters
   for cloud later.

---

## 2. System overview

```
┌─────────────────────┐        ┌──────────────────────────────────────────┐
│  React + TypeScript │        │              FastAPI backend              │
│                     │        │                                           │
│  Tenant dashboard   │  REST  │  API layer ──► Services ──► Repositories  │
│  Invoice review     │ ◄════► │  Auth · Tenant ctx · Permissions          │
│  Approval queue     │  JSON  │  Workflow state machine                   │
│  Analytics          │        └───────┬───────────────────┬──────────────┘
└─────────────────────┘                │                   │
                                       ▼                   ▼
                             ┌──────────────────┐  ┌──────────────────────┐
                             │   PostgreSQL     │  │   Redis + Celery     │
                             │ tenant-scoped    │  │  async workers       │
                             │ records + audit  │  │  retries · status    │
                             └──────────────────┘  └──────────┬───────────┘
                                                              │
                         ┌────────────────────────────────────┴───────────────────┐
                         ▼                ▼                ▼               ▼
                 ┌────────────┐  ┌────────────┐  ┌──────────────┐  ┌─────────────┐
                 │  Storage   │  │  OCR       │  │  LLM         │  │  ML         │
                 │  adapter   │  │  Tesseract │  │  provider    │  │  Isolation  │
                 │  (local/S3)│  │  /PyMuPDF  │  │  interface   │  │  Forest     │
                 └────────────┘  └────────────┘  └──────────────┘  └─────────────┘
```

### Component responsibilities

| Component | Responsibility |
| --- | --- |
| React frontend | Upload documents, display extracted fields, show errors, support review and approvals |
| FastAPI backend | Authentication, permissions, upload endpoints, business rules, invoice state transitions, APIs |
| PostgreSQL | Stores business records, processing status, extracted fields, approvals and audit events |
| Celery + Redis | Queues document-processing work and runs workers outside the API request |
| Processing pipeline | File validation → text extraction/OCR → LLM extraction → rule checks → duplicate checks → ML flags |
| Workflow engine | Routes valid invoices to approvers and exceptions to human review; sends notifications and records decisions |

---

## 3. Technology decisions

| Layer | Final decision | Notes |
| --- | --- | --- |
| Backend | Python, FastAPI, Pydantic | Type-safe schemas, OpenAPI generation |
| ORM & migrations | SQLAlchemy 2.x, Alembic | Migrations from day one |
| Database | PostgreSQL | `NUMERIC` money, strong constraints, composite keys |
| Frontend | React, TypeScript, Vite | Fast dev experience, typed API client |
| API communication | REST, JSON, OpenAPI | Documented contract |
| PDF parsing | PyMuPDF | Digital text extraction and page rendering |
| OCR | Tesseract initially; evaluate PaddleOCR | Inspect pages individually |
| LLM | External API behind provider interface | Structured output, Pydantic validation |
| Data & ML | Pandas, NumPy, scikit-learn | Isolation Forest baseline |
| Fuzzy matching | RapidFuzz | Supplier names, amounts, text |
| Background work | Celery and Redis | Retries, timeouts, idempotency |
| Tests | Pytest, HTTPX, frontend test tooling | Unit, integration, failure, security |
| Local environment | Docker Compose | db, redis, backend, worker, frontend |
| File storage | Private local storage adapter | Swappable for S3-compatible |
| Version control | Git and GitHub | Pinned dependencies |

Pin compatible dependency versions in the project files when the repository is
initialized.

---

## 4. Processing pipeline

```
        ┌────────────┐
Upload ─►│  Validate  │  size · extension · MIME · signature · path-traversal
        └─────┬──────┘
              ▼
        ┌────────────┐
        │   Store    │  server-generated id · tenant path · SHA-256 hash
        └─────┬──────┘
              ▼
        ┌────────────┐
        │    OCR     │  PyMuPDF per page → OCR only where no embedded text
        └─────┬──────┘
              ▼
        ┌────────────┐
        │    LLM     │  provider interface · structured output · Pydantic validation
        └─────┬──────┘
              ▼
        ┌────────────┐
        │ Validation │  deterministic rules (required fields, arithmetic, totals, tax)
        └─────┬──────┘
              ▼
        ┌────────────┐
        │ Duplicates │  file hash · normalized supplier+number · fuzzy match
        └─────┬──────┘
              ▼
        ┌────────────┐
        │    ML      │  Isolation Forest + statistical baselines · explainable flags
        └─────┬──────┘
              ▼
        ┌────────────┐
        │  Workflow  │  NEEDS_REVIEW or READY_FOR_APPROVAL → approval routing
        └────────────┘
```

### Extraction flow (detailed)

1. Extract embedded text from the PDF with PyMuPDF.
2. Run OCR on scanned pages where necessary.
3. Send only the necessary document content to the configured provider.
4. Request structured output using the invoice schema.
5. Validate the response with Pydantic.
6. Run deterministic business validations.
7. Save the extraction, provenance and errors.
8. Route missing, uncertain or inconsistent values to human review.

### Sequence — document processing

```
Frontend        FastAPI         PostgreSQL      Redis/Celery      Worker        Provider
   │  POST upload   │                │                │             │             │
   │───────────────►│  validate+store│                │             │             │
   │                │───────────────►│ metadata       │             │             │
   │                │  enqueue job   │                │             │             │
   │                │────────────────────────────────►│             │             │
   │  202 + id/status│               │                │  deliver    │             │
   │◄───────────────│                │                │────────────►│             │
   │                │                │                │             │  OCR+extract│
   │                │                │                │             │────────────►│
   │                │                │                │             │  structured │
   │                │                │                │             │◄────────────│
   │                │                │                │             │ validate/dupe/ML
   │                │                │◄───────────────┼─────────────│ persist     │
   │  GET status     │                │                │             │             │
   │───────────────►│  tenant-scoped read             │             │             │
   │◄───────────────│                │                │             │             │
```

Key properties:

- The API returns a document ID and processing status **without waiting for OCR**.
- Workers revalidate tenant context before processing (payloads carry tenant context).
- Retries are idempotent — reprocessing must not create duplicate business records.

---

## 5. Multi-tenant architecture

### 5.1 Tenant context resolution

```
Request
  └─► Auth dependency        → authenticated user identity
        └─► Membership check → user's active tenants + roles
              └─► Tenant ctx → TenantContext(tenant_id, actor_id, roles, permissions)
                    └─► Service layer requires TenantContext on every operation
                          └─► Repository filters: WHERE tenant_id = :ctx AND id = :id
```

Rules:

- Never trust a browser-supplied `tenant_id` on its own; validate membership.
- Services require tenant context; repositories always filter by `tenant_id` **and** the
  record id.
- Composite foreign keys (or equivalent constraints) prevent cross-tenant relationships.
- Background jobs carry tenant context and revalidate access before processing.
- Cache keys, file paths, duplicate checks and analytics are tenant-scoped.
- Cross-tenant isolation tests exist for every major resource.
- One tenant's history is never used to score another tenant's anomaly model.

### 5.2 Isolation layers (defense in depth)

| Layer | Control |
| --- | --- |
| Authentication | Bearer JWT identifies the user; membership determines tenants |
| Authorization | Role/permission checks per route and service call |
| Service | TenantContext is a required parameter; no unprotected data access |
| Repository/ORM | Every query filters by `tenant_id` |
| Database | Non-null `tenant_id`, composite FKs, tenant-scoped unique constraints |
| Storage | Tenant-prefixed paths resolved only through authorized backend operations |
| Workers | Tenant context in payload; revalidated before side effects |
| Optional (later) | PostgreSQL row-level security as defense in depth |

> A `tenant_id` column alone does not guarantee isolation. See
> [`security.md`](security.md) for the full threat model.

### 5.3 Local file storage layout

```
storage/
  tenants/
    <tenant-id>/
      documents/
        <document-id>/
          original.pdf
```

The directory structure is organizational, not a security boundary. Server-generated
identifiers, MIME/signature checks and authorized resolution are the real controls.

---

## 6. Provider abstraction (LLM/OCR)

The pipeline depends on interfaces so providers can change without touching business
logic.

```
backend/app/integrations/
├── llm/
│   ├── base.py          # InvoiceExtractionProvider protocol
│   ├── <provider>.py    # concrete implementation
│   └── schema.py        # structured-output schema + version
├── ocr/
│   ├── base.py          # OcrEngine protocol
│   └── tesseract.py
└── storage/
    ├── base.py          # StorageBackend protocol
    └── local.py
```

Illustrative interface:

```python
class InvoiceExtractionProvider:
    async def extract_invoice(self, document_text: str) -> dict: ...
```

Provider requirements:

- Credentials in environment variables or a secrets manager.
- Timeouts, bounded retries and usage limits.
- Persist provider/model identifiers and extraction-schema versions.
- Treat output as untrusted; validate with Pydantic; defend against prompt injection.
- Never let the provider choose tenant identity, permissions or approval authority.
- Manual-review fallback when the provider is unavailable.

---

## 7. Backend layering

```
api/            Thin HTTP layer: parse request, call service, return schema
  │
core/           Cross-cutting: config, security, permissions, tenant_context
  │
services/       Business rules and orchestration (document, extraction, validation,
  │             duplicate, approval, workflow state machine)
  │
db/models/      SQLAlchemy models — tenant-scoped
  │
integrations/   External systems behind interfaces (llm, ocr, storage, email)
  │
workers/        Celery tasks invoking services idempotently
```

Rules:

- Routes do not contain business logic.
- Services are the only place allowed to mutate business state.
- The workflow state machine is defined in exactly one service.
- Integrations are injected so they can be stubbed in tests.

---

## 8. Workflow engine and state machine

```
UPLOADED ─► QUEUED ─► PROCESSING ─┬─► NEEDS_REVIEW ─┐
                                  │                 ▼
                                  └─► READY_FOR_APPROVAL ─► APPROVED
                                          │  ▲
                                          ▼  │
                              CORRECTION_REQUESTED
Terminal/recovery: REJECTED · FAILED
```

- The allowed transition table lives in one workflow service.
- Each transition checks permission + current state + tenant.
- Each transition writes an audit event (actor, timestamp, reason).
- A worker cannot approve an invoice; only an authorized human decision can.

---

## 9. Background processing

- Celery workers handle OCR, LLM calls, validation, duplicate checks and ML scoring.
- Tasks are idempotent: use task/idempotency keys so retries do not duplicate records.
- Configure timeouts, bounded retries and dead-letter/failed-job handling.
- Track job status (`processing_jobs`) and expose it to the dashboard.
- Emit structured logs with job id, tenant id, stage and duration — never invoice
  contents or secrets.

---

## 10. Observability

| Signal | Source |
| --- | --- |
| Job status, attempts, errors | `processing_jobs`, task logs |
| Processing time per stage | Structured logs / metrics |
| Provider failures | Integration wrapper logs + metrics |
| Workflow bottlenecks | Aggregate query over states and timestamps |

Never log passwords, secret keys or unnecessary sensitive invoice contents.

---

## 11. Folder structure

```
ai-business-automation/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── auth.py
│   │   │   ├── tenants.py
│   │   │   ├── documents.py
│   │   │   ├── invoices.py
│   │   │   ├── approvals.py
│   │   │   └── analytics.py
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   ├── security.py
│   │   │   ├── permissions.py
│   │   │   └── tenant_context.py
│   │   ├── db/
│   │   │   ├── session.py
│   │   │   └── models/
│   │   ├── schemas/
│   │   ├── services/
│   │   │   ├── document_service.py
│   │   │   ├── extraction_service.py
│   │   │   ├── validation_service.py
│   │   │   ├── duplicate_service.py
│   │   │   └── approval_service.py
│   │   ├── integrations/
│   │   │   ├── llm/
│   │   │   ├── ocr/
│   │   │   └── storage/
│   │   ├── ml/
│   │   ├── workers/
│   │   └── main.py
│   ├── migrations/
│   └── tests/
├── frontend/
│   └── src/
│       ├── components/
│       ├── pages/
│       ├── features/
│       ├── services/
│       ├── hooks/
│       └── types/
├── data/
│   └── synthetic/
├── docs/
│   ├── requirements.md
│   ├── architecture.md
│   ├── database.md
│   ├── security.md
│   ├── api.md
│   └── roadmap.md
├── storage/                 # local only; never commit
├── docker-compose.yml
├── .env.example
├── .gitignore
└── README.md
```

---

## 12. Local environment (Docker Compose)

| Service | Image / build | Purpose |
| --- | --- | --- |
| `db` | postgres | Persistent, health-checked database |
| `redis` | redis | Celery broker/result backend |
| `backend` | backend/ | FastAPI app |
| `worker` | backend/ | Celery worker |
| `frontend` | frontend/ | Vite dev server / static build |

Requirements: health checks and persistent database storage. Keep uploaded files out of
images; mount `storage/` as a local volume.

---

## 13. Testing strategy

| Layer | Tooling | Focus |
| --- | --- | --- |
| Unit | Pytest | Rules, normalization, matching, policy logic |
| API/integration | Pytest + HTTPX | Endpoints, persistence, auth, transitions |
| Isolation | Pytest fixtures (two tenants) | Cross-tenant read/write denial on every resource |
| Failure | Pytest + fakes | Unreadable PDFs, provider timeouts, Redis loss, retries |
| Frontend | Project tooling | Components, forms, API states |
| ML | Pytest + notebooks/scripts | Accuracy, precision/recall, leakage checks |

---

## 14. Key architectural decisions (ADR summary)

| # | Decision | Rationale |
| --- | --- | --- |
| ADR-1 | Shared DB, shared tables, mandatory `tenant_id` | Simple to operate; adequate for portfolio; RLS later |
| ADR-2 | Application-level isolation first, RLS as defense in depth | Correct, testable controls before DB hardening |
| ADR-3 | Provider interface for LLM | Avoid vendor lock-in; enable local model later |
| ADR-4 | Deterministic validation in code | Financial correctness must be explainable and testable |
| ADR-5 | Single workflow state machine service | One source of truth for transitions and auditing |
| ADR-6 | Celery + Redis for slow work | Keep API responsive; enable retries/idempotency |
| ADR-7 | Local storage behind an interface | Secure local dev now; S3-compatible later |
| ADR-8 | Decimal money + explicit currency | Avoid floating-point errors; avoid cross-currency sums |
| ADR-9 | Versioned validation/anomaly records | Preserve history; never overwrite audit-relevant results |
