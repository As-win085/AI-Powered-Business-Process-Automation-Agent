# Database Design

> AI-Powered Business Process Automation Agent — Version 1.0 · October 2026

This document defines the relational schema, ownership, relationships and constraints.
It complements [`architecture.md`](architecture.md) and [`security.md`](security.md).

---

## 1. Design principles

1. **Shared database, shared tables, mandatory `tenant_id`.** Appropriate for a
   portfolio project and simpler to operate than one database per tenant.
2. **Non-guessable identifiers.** UUID primary keys.
3. **Tenant-scoped uniqueness** on appropriate business keys (e.g. normalized supplier
   invoice identifiers).
4. **Tenant consistency in foreign keys** where possible (composite keys or equivalent
   constraints).
5. **Separation of concerns:** the original file, document metadata and processing status
   are stored separately from invoice business fields.
6. **Extracted data is separate from line items.**
7. **Versioned validation/anomaly records** rather than overwriting history.
8. **Approval decisions are auditable events** with acting user, timestamp and reason.
9. **Alembic migrations from the beginning.**
10. **Test rollback, uniqueness constraints and concurrent updates.**

Global reference data may be tenant-independent; all business data is tenant-scoped.

---

## 2. Core entity relationships

```
                          ┌─────────┐
                          │ tenants │
                          └────┬────┘
             ┌─────────────────┼───────────────────────────────┐
             ▼                 ▼                               ▼
      ┌──────────────┐   ┌─────────────────┐            ┌────────────┐
      │   users      │◄─►│tenant_memberships│           │ suppliers  │
      └──────┬───────┘   └────────┬────────┘            └─────┬──────┘
             │                    │ roles/permissions          │
             │                    │                            │
             ▼                    ▼                            ▼
      ┌────────────────────────────────────────────┐    ┌──────────────────┐
      │                 documents                   │    │ purchase_orders  │
      │  (file metadata, hash, status)              │    │  + po_items      │
      └───────────────────┬─────────────────────────┘    └────────┬─────────┘
                          ▼                                        │
                    ┌───────────┐                                  │
                    │ invoices  │◄─────────────────────────────────┘
                    └─────┬─────┘
          ┌───────────────┼────────────────┬─────────────────┬─────────────┐
          ▼               ▼                ▼                 ▼             ▼
   invoice_line_     validation_      duplicate_        anomaly_      approvals
      items           results        candidates        results
                          │
                          ▼
                 processing_jobs · notifications · audit_logs
```

---

## 3. Tables

All tenant-owned tables carry a non-null `tenant_id`. `id` columns are UUIDs unless
noted. Timestamps are stored in UTC.

### 3.1 tenancy and identity

| Table | Key fields | Purpose |
| --- | --- | --- |
| `tenants` | `id`, `name`, `slug`, `status`, `settings` (JSON), `created_at` | Organization/tenant record; per-tenant config (currency, locale, tax, tolerances) |
| `users` | `id`, `email` (unique), `password_hash`, `full_name`, `is_active`, `created_at` | Global user identity |
| `tenant_memberships` | `id`, `tenant_id`, `user_id`, `role_id`, `status`, `created_at` | Links users to tenants; unique (`tenant_id`, `user_id`) |
| `roles` | `id`, `tenant_id` (nullable for system roles), `name`, `is_system` | Role definitions |
| `permissions` | `id`, `code`, `description` | Permission catalogue (global) |
| `role_permissions` | `role_id`, `permission_id` | Role → permission mapping |

### 3.2 master data

| Table | Key fields | Purpose |
| --- | --- | --- |
| `suppliers` | `id`, `tenant_id`, `name`, `normalized_name`, `tax_identifier`, `default_currency`, `status`, `created_at` | Supplier master data; unique (`tenant_id`, `tax_identifier`) where present |

### 3.3 documents and processing

| Table | Key fields | Purpose |
| --- | --- | --- |
| `documents` | `id`, `tenant_id`, `storage_key`, `original_filename`, `content_type`, `size_bytes`, `file_hash`, `document_type`, `status`, `page_count`, `uploaded_by`, `created_at` | Original file metadata and processing state; unique (`tenant_id`, `file_hash`) for exact-duplicate detection |
| `document_text` | `id`, `tenant_id`, `document_id`, `page_number`, `text`, `source` (`embedded`/`ocr`), `engine`, `created_at` | Extracted text per page with provenance |
| `processing_jobs` | `id`, `tenant_id`, `document_id`, `job_type`, `status`, `attempts`, `max_attempts`, `idempotency_key` (unique), `error`, `started_at`, `finished_at` | Task state, retries and failures |

### 3.4 invoices

| Table | Key fields | Purpose |
| --- | --- | --- |
| `invoices` | `id`, `tenant_id`, `document_id`, `supplier_id`, `purchase_order_id`, `invoice_number`, `normalized_invoice_number`, `invoice_date`, `due_date`, `currency`, `subtotal`, `tax_amount`, `total_amount`, `state`, `risk_level`, `created_at`, `updated_at` | Invoice header fields; unique (`tenant_id`, `supplier_id`, `normalized_invoice_number`) |
| `invoice_extractions` | `id`, `tenant_id`, `invoice_id`, `provider`, `model`, `schema_version`, `raw_output` (JSONB), `confidence` (JSONB), `created_at` | Versioned extraction attempts with provenance (preserves history across reprocessing) |
| `invoice_line_items` | `id`, `tenant_id`, `invoice_id`, `line_number`, `description`, `quantity`, `unit_price`, `tax_amount`, `line_total`, `created_at` | Item-level invoice data |

### 3.5 purchase orders

| Table | Key fields | Purpose |
| --- | --- | --- |
| `purchase_orders` | `id`, `tenant_id`, `supplier_id`, `po_number`, `currency`, `total_amount`, `status`, `created_at` | Purchase order records; unique (`tenant_id`, `po_number`) |
| `purchase_order_items` | `id`, `tenant_id`, `purchase_order_id`, `line_number`, `description`, `quantity`, `unit_price`, `line_total` | Item-level PO data |

### 3.6 decision support (versioned)

| Table | Key fields | Purpose |
| --- | --- | --- |
| `validation_results` | `id`, `tenant_id`, `invoice_id`, `run_id`, `rule_name`, `severity`, `passed`, `details` (JSONB), `created_at` | Validation findings and explanations; grouped by `run_id` |
| `duplicate_candidates` | `id`, `tenant_id`, `invoice_id`, `candidate_invoice_id`, `match_type` (`exact_file`/`business`/`fuzzy`), `score`, `signals` (JSONB), `status`, `created_at` | Duplicate flags without silently discarding records |
| `anomaly_results` | `id`, `tenant_id`, `invoice_id`, `model_version`, `score`, `is_flagged`, `explanation` (JSONB), `created_at` | ML/statistical anomaly scores and explainable signals |

### 3.7 workflow and audit

| Table | Key fields | Purpose |
| --- | --- | --- |
| `approvals` | `id`, `tenant_id`, `invoice_id`, `approver_id`, `decision`, `comments`, `decided_at`, `state_before`, `state_after` | Approval decisions as auditable events |
| `approval_policies` | `id`, `tenant_id`, `name`, `min_amount`, `max_amount`, `required_role_id`, `active` | Configurable routing rules |
| `notifications` | `id`, `tenant_id`, `recipient_id`, `type`, `payload` (JSONB), `status`, `created_at`, `read_at` | Approval requests, reminders, failure notices |
| `audit_logs` | `id`, `tenant_id`, `actor_id`, `entity_type`, `entity_id`, `action`, `changes` (JSONB), `created_at` | Who changed/approved what and when; protected from modification |

---

## 4. Schema rules (mandatory)

1. Every tenant-owned table has a **non-null `tenant_id`**.
2. Use **UUID** identifiers (or another consistent non-guessable strategy).
3. Add **tenant-scoped uniqueness** constraints where appropriate, such as normalized
   supplier invoice identifiers.
4. Make **tenant consistency part of FK relationships** where possible — e.g. composite
   FKs `(tenant_id, invoice_id)` referencing `invoices(tenant_id, id)`.
5. Store the **original file hash, document metadata and processing status separately**
   from invoice business fields.
6. Store **extracted invoice data separately from line items**.
7. Store **validation and anomaly results as versioned records** rather than overwriting
   all history.
8. Record **approval decisions as auditable events** with acting user, timestamp and
   reason.
9. Use **Alembic migrations** from the beginning.
10. **Test rollback, uniqueness constraints and concurrent updates.**

### 4.1 Composite foreign key pattern

Because both `invoices` and the child tables carry `tenant_id`, foreign keys are
composite so a child can never reference a parent in another tenant:

```sql
-- parent must expose a unique (tenant_id, id)
ALTER TABLE invoices ADD CONSTRAINT uq_invoices_tenant_id UNIQUE (tenant_id, id);

-- child references (tenant_id, invoice_id) → invoices(tenant_id, id)
ALTER TABLE invoice_line_items
  ADD CONSTRAINT fk_line_items_invoice
  FOREIGN KEY (tenant_id, invoice_id) REFERENCES invoices (tenant_id, id)
  ON DELETE CASCADE;
```

This makes cross-tenant relationships impossible at the database level, not just in
application code.

---

## 5. Money, currency and time

- Money columns use `NUMERIC(precision, scale)` — never binary floating point.
- Every monetary context carries an explicit ISO 4217 currency code.
- Do not sum different currencies as though they were the same currency.
- If exchange-rate conversion is introduced later, record rate source, rate date and
  original amounts.
- Store all timestamps in UTC. Format for display using the tenant locale.

---

## 6. Indexing strategy

| Table | Index | Reason |
| --- | --- | --- |
| `tenant_memberships` | (`tenant_id`, `user_id`) unique | Membership lookup and enforcement |
| `users` | `email` unique | Login |
| `suppliers` | (`tenant_id`, `normalized_name`), (`tenant_id`, `tax_identifier`) | Matching and uniqueness |
| `documents` | (`tenant_id`, `file_hash`), (`tenant_id`, `status`) | Duplicate detection, queue views |
| `invoices` | (`tenant_id`, `supplier_id`, `normalized_invoice_number`), (`tenant_id`, `state`), (`tenant_id`, `invoice_date`) | Uniqueness, workflow, reporting |
| `validation_results` | (`tenant_id`, `invoice_id`, `run_id`) | Latest validation set |
| `duplicate_candidates` | (`tenant_id`, `invoice_id`), (`tenant_id`, `candidate_invoice_id`) | Review queues |
| `anomaly_results` | (`tenant_id`, `invoice_id`, `model_version`) | Latest score |
| `processing_jobs` | `idempotency_key` unique, (`tenant_id`, `status`) | Idempotency, monitoring |
| `audit_logs` | (`tenant_id`, `entity_type`, `entity_id`), (`tenant_id`, `created_at`) | Audit reconstruction |

All indexes are **tenant-prefixed** so tenant-scoped queries are efficient and cannot
accidentally scan across tenants.

---

## 7. Migration strategy (Alembic)

- Migrations from the first commit; no `create_all()` in production paths.
- One logical change per migration with a clear message.
- Every migration implements both `upgrade()` and `downgrade()`.
- Milestone 1 migration adds `tenants`, `users`, `tenant_memberships` (plus roles,
  permissions, `role_permissions`) with FKs, unique constraints and status fields.
- Later migrations add documents, invoices, decision-support and workflow tables.
- CI/test runs apply migrations against a clean database, then verify rollback.

Suggested ordering (as implemented):

```
0001  tenancy_identity      tenants, users, tenant_memberships, roles,
                            permissions, role_permissions
0002  business_documents    suppliers, documents, processing_jobs,
                            purchase_orders(+items), invoices(+line_items),
                            validation_results, approvals(+history), audit_logs
```

Revision `0002` consolidates the business-model tables from several of the suggested
milestone migrations so Week-1 backend work ships in one revision; later milestones
(OCR text, extraction versions, duplicate/anomaly results, policies, notifications)
will add their own revisions.

---

## 8. Concurrency and integrity tests

- **Rollback:** `alembic upgrade head` → `alembic downgrade -1` → `upgrade head` succeeds.
- **Uniqueness:** inserting a duplicate (`tenant_id`, `supplier_id`,
  `normalized_invoice_number`) fails as expected.
- **Isolation at the DB:** a composite FK rejects a child row whose `tenant_id` differs
  from its parent.
- **Concurrent updates:** two simultaneous state transitions on one invoice do not both
  succeed; the second fails or is serialized.
- **Idempotency:** reprocessing a document with the same idempotency key does not create
  duplicate jobs or business records.

---

## 9. Future extension (not required for v1)

- A dedicated `invoice_extractions` table already preserves multiple extraction attempts;
  if extraction volume grows, split provenance from the invoice row further.
- Goods-received records for three-way matching.
- Exchange-rate table with source, date and original amounts.
- Optional PostgreSQL row-level security policies for defense in depth.
- Optional separate database-per-tenant for highest-isolation deployments.
