# Implementation Roadmap

> AI-Powered Business Process Automation Agent — Version 1.0 · October 2026

Two complementary views of the same plan:

- **Milestone gates** — the primary workflow. Move forward **only** when the previous
  milestone's acceptance tests pass.
- **8-week timeline** — an indicative schedule mapping the same work to weeks.

Do **not** begin with the LLM, OCR or ML model. First establish a secure foundation that
those components can safely use.

---

## Milestone-driven plan (primary)

### Milestone 1 — Foundation and tenant isolation

**Start here.**

- Repository, configuration, Docker Compose, PostgreSQL, migrations.
- Tenants, users, memberships, roles/permissions.
- Authentication and tenant-scoped test fixtures.

**Gate:** tests prove Tenant A cannot read or modify Tenant B's records.

> **Status:** foundation complete. Backend Milestone 1 (tenants, auth, isolation)
> and Phase 1 Week-1 backend work are done — **41 tests passing**, including the
> cross-tenant isolation gate, document upload (magic-byte validation + SHA-256 +
> private storage), filtered/paginated list & detail, tenant-scoped audit API and
> business-model migration `0002`. Frontend shell (item 9 below) and the initial
> commit (item 10) remain, by request.

#### Milestone 1 checklist

- [x] 1. Create the Git repository — backend, frontend and docs directories; README, `.gitignore`, `.env.example`.
- [x] 2. Initialize the Python backend — venv; FastAPI, Uvicorn, Pydantic Settings, SQLAlchemy, Alembic, PostgreSQL driver.
- [x] 3. Create Docker Compose — PostgreSQL and Redis with health checks and persistent storage.
- [x] 4. Configure application settings — database URL, JWT settings, storage root, LLM provider settings from environment variables.
- [x] 5. Create the first migration — `tenants`, `users`, `tenant_memberships` with FKs, unique constraints and status fields.
- [x] 6. Implement authentication — secure password hashing, login, current-user resolution; test expired/invalid credentials.
- [x] 7. Implement tenant context — resolve active tenant from an authenticated membership; enforce tenant filters in services.
- [x] 8. Write isolation tests — two test tenants; prove neither can access the other's records.
- [ ] 9. Build the first frontend shell — React + TypeScript app with login, authenticated routing and an organization selector.
- [ ] 10. Document and commit — setup commands, migration steps, tests; commit the working foundation.

**Initial backend dependencies**

```bash
pip install fastapi "uvicorn[standard]" pydantic-settings \
  sqlalchemy alembic "psycopg[binary]" \
  pwdlib pyjwt python-multipart pytest httpx
```

Configure password hashing and JWT algorithms using current package documentation. Pin
working versions in a dependency file after installation.

---

### Milestone 2 — Documents and persistence

- Private local storage adapter and directory layout.
- Upload validation (size, extension, MIME, signature, path traversal).
- File hashing, document list/detail APIs.
- Basic React upload/review screens.

**Gate:** authorized upload and retrieval work; invalid files are rejected.

> **Status:** backend half complete — `Storage` interface + `LocalStorage`
> (path-traversal safe), upload validation (size via `413`, extension/MIME/magic
> bytes via `422`), SHA-256 duplicate rejection (`409`), list/detail/download APIs
> with pagination and a `log_audit(...)` audit trail are implemented and tested.
> The React upload/review screens remain.

---

### Milestone 3 — Extraction and validation

- PyMuPDF text extraction and OCR fallback.
- Provider abstraction and structured invoice schema.
- Human correction and deterministic calculation rules.

**Gate:** representative invoices can be extracted, reviewed and persisted without losing
original values.

---

### Milestone 4 — Duplicate detection and approvals

- Exact and fuzzy matching; purchase-order comparison.
- Workflow state machine, approval permissions, audit history, notifications.

**Gate:** duplicate cases are flagged and valid/invalid approval paths are tested.

---

### Milestone 5 — ML and background processing

- Celery workers, Redis, retry and idempotency controls.
- Anomaly features, Isolation Forest baseline, evaluation report.

**Gate:** repeat processing is safe; model limitations and evaluation results are
documented.

---

### Milestone 6 — Portfolio release

- Dashboard, end-to-end tests, security checks.
- Documentation, demo data, screenshots, deployment if appropriate.

**Gate:** another developer can follow the README and reproduce the application locally.

---

## Indicative 8-week timeline

| Week | Focus | Definition of done |
| --- | --- | --- |
| 1 | Project setup and backend foundation — repo/folders, FastAPI, PostgreSQL, env vars, Docker Compose, models and migrations, auth and roles, upload and list endpoints | A user can sign in, upload a document and see it in the dashboard |
| 2 | Document storage and OCR — PyMuPDF text, OCR for scans, multi-page/poor scans, store text and status, original/OCR viewer | The app extracts text from digital PDFs and scanned invoices |
| 3 | LLM structured extraction — Pydantic invoice schema, extraction service, missing/ambiguous handling, field-correction UI | A user can upload an invoice and correct the extracted data |
| 4 | Validation and duplicates — required-field and arithmetic checks, identifier normalization, file-hash and exact-match, fuzzy similarity, severity and explanations | The app identifies common errors and duplicate candidates |
| 5 | ML model and evaluation — synthetic/historical data, supplier/amount/frequency features, Isolation Forest baseline, evaluate vs labels/expert review, track false positives and versions | Measurable anomaly scores and review flags |
| 6 | Purchase-order matching and approvals — PO records, match supplier/quantities/prices, states and policies, approve/reject/correction, prevent unauthorized/repeated decisions | Validated invoices enter an auditable approval workflow |
| 7 | Background automation and notifications — Celery/Redis, retries and timeouts, approval requests and reminders, idempotent tasks, structured logs and metrics | Documents process asynchronously and recover from transient failures |
| 8 | Testing, deployment and documentation — unit/API/workflow tests, malformed files, retries, permissions, dashboard and analytics, Docker deploy, README and measured results | A deployed app with tests, documentation and a demonstrable workflow |

**Mapping:** Weeks 1–2 ≈ Milestones 1–2; Weeks 3–4 ≈ Milestones 3–4; Week 5 ≈
Milestone 5; Weeks 6–7 ≈ Milestone 4–5 remainder; Week 8 ≈ Milestone 6.

---

## AI/ML pipeline implementation notes

### A. OCR and text extraction

Check for selectable text first. Use PyMuPDF for digital text; OCR only for scanned pages.
Real files may mix both, so inspect **pages individually** and handle rotation, malformed
files and OCR failures.

### B. LLM-based structured extraction

Provide OCR text to an LLM and request output matching a Pydantic schema. Schema validation
ensures structure, **not factual correctness**. Preserve missing/ambiguous values and
require human verification for important fields.

```python
from datetime import date
from decimal import Decimal
from pydantic import BaseModel

class InvoiceData(BaseModel):
    supplier_name: str
    invoice_number: str
    invoice_date: date | None
    subtotal: Decimal | None
    tax_amount: Decimal | None
    total_amount: Decimal | None
    currency: str
```

### C. Deterministic validation

Use normal Python logic for arithmetic and policy checks (e.g. `subtotal + tax = total`).
Production rules must account for discounts, shipping, rounding, credit notes and
invoice-specific tax treatment.

### D. Duplicate detection

- **Exact file duplicate:** compare cryptographic file hashes.
- **Business duplicate:** compare normalized supplier identity and invoice number.
- **Near-duplicate:** compare supplier, amount, date, line items and text similarity.

### E. ML anomaly detection

Start with scikit-learn Isolation Forest and compare against simple statistical baselines.
Candidate features: invoice amount vs. supplier historical median, difference from
purchase-order value, invoice frequency, and changes within an expense category. Split data
by time where possible to reduce leakage. Without reliable labels, the model identifies
**unusual records — not confirmed fraud.**

---

## Metrics to track

| Metric | What it measures |
| --- | --- |
| Field-level extraction accuracy | Extracted fields matching ground truth |
| Duplicate precision / recall | Genuine flags vs. known duplicates found |
| Anomaly precision / recall | Performance on labeled test cases |
| Processing latency | Upload → completed processing |
| Background-job success rate | Jobs completing including transient-failure recovery |
| Manual correction rate | Frequency of user field corrections |
| Workflow completion rate | Share reaching a valid final state |

Collect around 100–300 representative invoices (clean, duplicates, missing fields,
calculation errors, varied layouts, unusual transactions). Use synthetic or licensed data.
**Report measured results only.**

---

## Working agreements

- Milestone gates pass before the next milestone begins.
- Keep business rules in services, never in routes or UI.
- Every tenant-owned resource ships with a cross-tenant isolation test.
- Secrets never enter Git; `.env` stays local.
- Update docs and this roadmap when commands, structure or scope change.
