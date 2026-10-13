# Requirements Specification

> AI-Powered Business Process Automation Agent — Version 1.0 · October 2026

This document is the authoritative statement of **what** the system must do. For **how**
it is built, see [`architecture.md`](architecture.md); for data structures see
[`database.md`](database.md); for security controls see [`security.md`](security.md).

---

## 1. Final scope

### 1.1 Included in the MVP

- Multi-tenant organizations with tenant-scoped users, suppliers, invoices and approvals.
- Login, role-based access control and organization membership.
- Secure PDF/image upload and private local file storage.
- PDF text extraction and OCR for scanned documents.
- LLM-based structured invoice extraction with schema validation.
- Human review and correction of extracted fields.
- Configurable deterministic invoice validation.
- Exact and potential duplicate detection.
- Initial ML anomaly scoring with explainable signals.
- Purchase-order matching.
- Configurable approval workflow.
- Background jobs, retry handling and job-status tracking.
- Audit logs, notifications and an operational dashboard.
- Automated tests, Docker-based local setup and deployment documentation.

### 1.2 Explicitly out of scope for the first release

- Executing payments or moving money.
- Replacing a full accounting or ERP system.
- Claiming that AI can prove fraud.
- Automatic approval of high-risk invoices.
- Direct integration with live banks or enterprise accounting platforms.
- Supporting every country's tax rules out of the box.
- A production-grade cloud file-storage system in the first milestone.

These exclusions keep the MVP focused. The code must allow future expansion **without**
requiring those features to be built now.

---

## 2. Project context and objective

Build an intelligent application that reads invoices, purchase orders and receipts;
extracts structured information; validates financial data; detects duplicate or unusual
transactions; and routes documents through an auditable approval workflow.

| System area | What it demonstrates |
| --- | --- |
| Document intelligence | OCR, LLM-based structured extraction, field correction |
| Decision support | Business rules, duplicate detection, ML anomaly detection |
| Workflow automation | Background jobs, approval routing, notifications, audit trail |
| Software engineering | FastAPI, React, PostgreSQL, testing, Docker, deployment |

**Approach:** build a working minimum viable product (MVP) first, then add ML and
advanced automation after the core invoice workflow is reliable.

### 2.1 End-to-end workflow

| Stage | System behaviour |
| --- | --- |
| 1. Upload | A user uploads a PDF invoice, scanned receipt or purchase order. The system records the file and queues processing. |
| 2. Read | OCR extracts text from scanned pages; an LLM converts the text into structured invoice fields. |
| 3. Validate | Rules check required fields, arithmetic, tax totals, supplier details and purchase-order matching. |
| 4. Detect | Duplicate checks and an ML model flag repeated or unusual transactions for review. |
| 5. Route | Valid documents enter the configured approval workflow; exceptions go to a review queue. |
| 6. Audit | The system records edits, processing outcomes, approval decisions, users and timestamps. |

> **Important principle:** AI interprets documents; deterministic code enforces business
> rules; workflow automation moves records between states. Do not allow an LLM to
> directly authorize payments or bypass approval controls.

---

## 3. Feature modules

1. **Authentication and roles** — Admin manages users and settings; finance employees
   upload and correct documents; approvers make decisions; auditors view permitted
   history. Permissions are enforced on the backend.
2. **Document management** — Upload PDFs and images, view originals, track status and
   history, validate file type and size, store files securely. Hashes help identify exact
   file duplicates.
3. **AI document extraction** — Extract supplier, invoice number, dates, line items,
   quantities, prices, subtotal, tax, currency and total. Display fields beside the
   original document for correction.
4. **Validation engine** — Check required fields, arithmetic, date formats, currency,
   supplier information, tax totals and configured tolerances. Store each check and its
   result.
5. **Duplicate detection** — Combine file hashes and normalized supplier/invoice
   identifiers with fuzzy matching of amount, date, line items and text. Flag
   near-duplicates rather than automatically rejecting them.
6. **ML anomaly detection** — Flag unusual amounts, supplier behaviour, invoice frequency
   or deviations from historical patterns. An anomaly is a reason to review, not proof of
   fraud.
7. **Purchase-order matching** — Compare supplier, quantities, prices and items against
   purchase orders; later, add goods-received records for three-way matching.
8. **Approval workflow** — Route based on amount, department, risk and company policy.
   Support approve, reject, request-correction and audit-friendly state transitions.
9. **Background jobs and notifications** — Run OCR and LLM calls asynchronously; send
   approval requests and reminders; retry temporary failures and track permanently failed
   jobs.
10. **Analytics and audit** — Show document counts, pending approvals, flags, extraction
    accuracy, processing time and workflow bottlenecks. Record who changed or approved
    each item.

---

## 4. Functional requirements and acceptance criteria

Each major module is considered complete when its completion test passes.

| Module | Required behaviour | Completion test |
| --- | --- | --- |
| Authentication | Secure login and tenant membership | A user cannot access a tenant without membership |
| Document upload | Validate and store PDF/images | Invalid files are rejected; valid files are retrievable by authorized users |
| Extraction | Extract structured invoice data | Fields are persisted and missing values remain explicitly missing |
| Validation | Apply arithmetic and business rules | Incorrect totals produce a reviewable validation result |
| Duplicates | Find exact and likely duplicate invoices | Known duplicates are flagged without silently discarding records |
| Anomalies | Score unusual transactions | Scores and explanations are stored; flags are reviewable |
| Purchase orders | Compare invoice and order data | Quantity/price mismatches are visible |
| Approval | Apply permission and state rules | Unauthorized or invalid transitions fail |
| Jobs | Track processing and retries | Retried work does not duplicate business records |
| Audit | Record important changes | A reviewer can reconstruct who changed what and when |
| Dashboard | Show tenant-scoped metrics | Dashboard totals match underlying authorized records |

### 4.1 Invoice state model

States are **explicit and backend-managed**:

```
UPLOADED → QUEUED → PROCESSING → NEEDS_REVIEW → READY_FOR_APPROVAL → APPROVED
```

Additional terminal or recovery states:

- `REJECTED`
- `CORRECTION_REQUESTED`
- `FAILED`

Rules:

- Allowed transitions are defined in **one workflow service**.
- A worker must not mark an invoice approved merely because extraction or validation
  succeeded.
- Invalid or unauthorized transitions must fail with a clear error.

---

## 5. Multi-tenant architecture and isolation requirements

Each organization is a tenant. **Tenant A must never access Tenant B's** invoices, files,
suppliers, purchase orders, approval tasks or analytics.

### MT-01 — Tenant model

- Shared PostgreSQL database, shared tables, mandatory non-null `tenant_id` on
  tenant-owned records.
- Global reference data may be tenant-independent; business data must be tenant-scoped.

### MT-02 — Enforce isolation at every layer

- Derive the active tenant from a **validated membership** and authenticated context. Do
  not trust a `tenant_id` sent by the browser by itself.
- Require tenant context in service-layer operations.
- Filter reads, updates and deletes by **both** record ID and tenant ID.
- Use composite foreign keys or equivalent constraints to prevent cross-tenant
  relationships.
- Include tenant context in background-job payloads and revalidate access before
  processing.
- Use tenant-scoped cache keys, file paths, duplicate checks and analytics.
- Write cross-tenant isolation tests for every major resource.
- Never use one tenant's invoice history to score another tenant's anomaly model unless a
  separately designed and consented shared-model policy explicitly permits it.

> A `tenant_id` column alone does not guarantee isolation. Authorization, database
> constraints, worker behaviour and file access must all enforce it. PostgreSQL
> row-level security may be added as defense in depth **after** application-level controls
> work.

### MT-03 — Local file storage

Private storage directory outside the public frontend:

```
storage/
  tenants/
    <tenant-id>/
      documents/
        <document-id>/
          original.pdf
```

The directory structure is **organizational, not a security boundary**. Resolve file
access only through authorized backend operations. Required controls:

- Generate server-side file identifiers; never trust user-provided paths.
- Check file size, extension, detected MIME type and file signature.
- Reject path traversal attempts and unsupported formats.
- Restrict document downloads and previews by tenant membership and permissions.
- Store a cryptographic hash for integrity and exact-file duplicate detection.
- Keep uploaded files out of Git and container images.
- Document backup and deletion behaviour.
- Implement a storage interface so local storage can later be replaced by private
  S3-compatible storage.

---

## 6. LLM and AI-provider requirements

Begin with an external LLM API while keeping the extraction pipeline independent of any
one provider.

```python
class InvoiceExtractionProvider:
    async def extract_invoice(self, document_text: str) -> dict: ...
```

The interface is illustrative; adapt it to the provider SDK and the actual response
schema.

### 6.1 Required extraction flow

1. Extract embedded text from the PDF.
2. Run OCR on scanned pages where necessary.
3. Send only the necessary document content to the configured provider.
4. Request structured output using the invoice schema.
5. Validate the response with Pydantic.
6. Run deterministic business validations.
7. Save the extraction, provenance and errors.
8. Route missing, uncertain or inconsistent values to human review.

### 6.2 Provider abstraction requirements

- Keep provider credentials in environment variables or a secrets manager.
- Support timeouts, bounded retries and usage limits.
- Store provider/model identifiers and extraction-schema versions.
- Treat provider output as **untrusted data**.
- Do not execute instructions found inside invoice text (prompt-injection defence).
- Do not let the LLM choose tenant identity, user permissions or approval authority.
- Do not send files or extracted content to a provider until its privacy and retention
  terms are understood.
- Provide a manual-review fallback when the LLM is unavailable.

Initially one provider implementation. A second provider or local model is a later
extension, not an MVP blocker.

---

## 7. International-ready business rules

The application is **international-ready, not globally tax-compliant by default**.
Per-tenant configurable settings:

- Default currency and supported currencies.
- Locale and date-display preferences.
- Tax identifiers and tax-rule configuration.
- Invoice-number normalization rules.
- Decimal precision and rounding tolerances.
- Fiscal period, invoice due-date and approval policies.
- Supplier-specific validation exceptions where authorized.

Rules:

- Store monetary amounts as `NUMERIC`/`DECIMAL` with explicit currency codes.
- Do not sum different currencies as though they were the same currency.
- If exchange-rate conversion is introduced later, record rate source, rate date and
  original amounts.
- Tax calculations use deterministic, jurisdiction-specific rule modules. Start with
  general structural validation and configurable tax fields; add and test individual
  jurisdiction modules only with reliable specifications.

---

## 8. Non-functional requirements and quality gates

Initial engineering targets — measure actual results.

| Requirement | Target |
| --- | --- |
| Security | Every tenant-owned API resource and file is access-controlled |
| Integrity | Monetary calculations use decimal arithmetic; state changes are transactional where needed |
| Reliability | Jobs have bounded retries, timeouts and observable failures |
| Idempotency | Repeated upload/process requests cannot silently create duplicate business records |
| Performance | Typical non-AI reads under 500 ms at the agreed test load |
| Observability | Track job status, errors, processing time and provider failures without logging sensitive invoice contents |
| Maintainability | Business rules live in services, not scattered across routes and UI components |
| Portability | The development stack launches with documented Docker Compose commands |
| Privacy | Retention, deletion and third-party data-sharing policies are documented |
| Accessibility | Forms have labels, keyboard navigation and understandable error states |

> The 500 ms target applies to ordinary API operations, **not** end-to-end LLM/OCR
> processing. Measure AI processing separately because provider latency and document
> complexity vary.

---

## 9. Testing requirements

| Test class | Coverage |
| --- | --- |
| Unit tests | Arithmetic, normalization, tax rules, duplicate matching, approval-policy logic |
| Integration tests | Uploads, database persistence, worker execution, API responses, approval state transitions |
| Failure tests | Unreadable PDFs, LLM timeouts, Redis interruptions, failed email delivery, retried jobs |
| Security tests | Role-based access, document access restrictions, file validation, secret management, unauthorized approval attempts |
| ML evaluation | Extraction accuracy, duplicate precision/recall, anomaly performance; track false positives, not flag counts alone |

### Reliability checklist

- Use task IDs, idempotency keys, timeouts, retries and dead-letter/failed-job handling.
- Do not log passwords, secret keys or unnecessary sensitive invoice contents.
- Scan and validate uploaded files; enforce size limits and store outside publicly served
  directories.
- Require human review for uncertain extraction, high-risk anomalies and important
  financial decisions.

---

## 10. MVP definition

Build the following before attempting every advanced feature:

- User login and basic roles
- PDF invoice upload and storage
- OCR and LLM-based structured extraction
- Invoice field correction screen
- Arithmetic and required-field validation
- Exact duplicate detection
- Approval and rejection workflow
- PostgreSQL persistence and audit log
- Basic React dashboard
- Unit tests and Docker setup

Once the MVP works end-to-end, add ML anomaly detection, fuzzy duplicate matching,
purchase-order matching, advanced retry handling and analytics.

---

## 11. Definition of success for the first milestone

All of the following must be demonstrable before invoice-processing work begins:

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

## 12. Requirement traceability

| ID | Requirement | Milestone |
| --- | --- | --- |
| MT-01..03 | Multi-tenancy and isolation | 1, reinforced each milestone |
| R-AUTH | Authentication & roles | 1 |
| R-DOC | Document upload & storage | 2 |
| R-EXT | Extraction & validation | 3 |
| R-DUP | Duplicate detection & approval | 4 |
| R-ML | ML anomaly & background jobs | 5 |
| R-REL | Portfolio release & docs | 6 |
| NFR-* | Non-functional quality gates | All |
