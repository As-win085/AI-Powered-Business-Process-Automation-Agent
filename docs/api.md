# API Reference

> AI-Powered Business Process Automation Agent — Version 1.0 · October 2026

REST/JSON API. The backend generates OpenAPI documentation at `/docs` (Swagger) and
`/openapi.json`. All endpoints except `POST /api/auth/login` require authentication.

> **Always check permissions and state transitions on the server.** Hiding a button in
> React does not secure an endpoint. Every tenant-owned resource is filtered by the
> authenticated tenant context.

---

## Conventions

- **Base path:** `/api`
- **Auth:** `Authorization: Bearer <access_token>`
- **Tenant:** derived from the authenticated user's membership. A tenant selector may send
  `X-Tenant-Id`, which is validated against the membership — never trusted alone.
- **Content types:** `application/json`, `multipart/form-data` (uploads)
- **IDs:** UUID strings
- **Errors:** JSON with `detail`; standard codes (`400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`)
- **Pagination:** `limit` / `offset` (or cursor), tenant-scoped
- **Idempotency:** upload/process endpoints accept `Idempotency-Key` to prevent duplicates

---

## Endpoint summary

> Below is the target surface. **Implemented now** (backend foundation):
> `POST/GET /api/documents`, `GET /api/documents/{id}`, `GET /api/documents/{id}/download`,
> `GET /api/audit`, plus all `/api/auth/*` and `/api/tenants*` endpoints. Doc routes
> are `download` (streaming) rather than the planned `file` name, the audit route is
> `/api/audit` rather than `/api/audit-logs`, and uploads currently return `201` in an
> `uploaded` state (processing enqueue arrives with the worker milestone).

| Method | Endpoint | Purpose |
| --- | --- | --- |
| POST | `/api/auth/login` | Authenticate user |
| POST | `/api/auth/refresh` | Refresh access token |
| GET | `/api/auth/me` | Current user and memberships |
| GET | `/api/tenants` | List tenants the user belongs to |
| POST | `/api/documents` | Upload document |
| GET | `/api/documents` | List documents with filters |
| GET | `/api/documents/{id}` | View document metadata and status |
| GET | `/api/documents/{id}/file` | Stream original file (authorized) |
| POST | `/api/documents/{id}/process` | Request processing or reprocessing |
| GET | `/api/invoices/{id}` | View extracted invoice data |
| PATCH | `/api/invoices/{id}` | Correct extracted fields |
| GET | `/api/invoices/{id}/validations` | View validation results |
| GET | `/api/invoices/{id}/duplicates` | View duplicate candidates |
| GET | `/api/invoices/{id}/anomalies` | View anomaly score and explanation |
| GET | `/api/invoices/{id}/purchase-order` | View PO match results |
| GET | `/api/approvals` | Current user's approval queue |
| POST | `/api/approvals/{id}/decision` | Approve/reject (server-authorized) |
| GET | `/api/audit-logs` | View permitted audit history |
| GET | `/api/analytics/summary` | Dashboard metrics |

---

## Authentication

### POST `/api/auth/login`

Request:

```json
{ "email": "finance@acme.test", "password": "••••••••" }
```

Response `200`:

```json
{
  "access_token": "…",
  "refresh_token": "…",
  "token_type": "bearer",
  "expires_in": 1800
}
```

- `401` on invalid credentials. Failures are audited.

### GET `/api/auth/me`

Returns the user and the tenants/memberships they can access. This is the source for the
frontend organization selector.

### GET `/api/tenants`

Returns only tenants where the caller has an active membership.

---

## Documents

> **Implemented:** `POST /api/documents` returns `201` with the created `DocumentRead`
> (title-cased fields, e.g. `document_type`, `status`); list/detail/download are live.
> Reference payloads below describe the later queued-processing design.

### POST `/api/documents`

`multipart/form-data` — fields: `file` (required), `document_type`, `purchase_order_id` (optional).

- Validates size, extension, MIME type and file signature.
- Stores the file under a server-generated id and computes a SHA-256 hash.
- Enqueues a processing job and returns immediately (**does not wait for OCR**).

Response `202`:

```json
{
  "id": "…",
  "status": "QUEUED",
  "original_filename": "invoice-1234.pdf",
  "document_type": "invoice",
  "created_at": "2026-10-12T10:00:00Z"
}
```

- `400` invalid file, `413` too large, `409` exact-file duplicate (see duplicates policy).

### GET `/api/documents`

Query filters: `status`, `document_type`, `supplier_id`, `date_from`, `date_to`, `limit`, `offset`.
Returns only the caller's tenant documents.

### GET `/api/documents/{id}`

Metadata and current processing status. `404` if not in the caller's tenant.

### GET `/api/documents/{id}/file`

Streams the original file after authorization. Never statically served.

### POST `/api/documents/{id}/process`

Requests processing or reprocessing. Idempotent via `Idempotency-Key`; reprocessing does
not duplicate business records. `409` if a job is already running.

---

## Invoices

### GET `/api/invoices/{id}`

Returns extracted header fields, line items, current state, provenance (provider/model,
schema version) and which values are missing.

### PATCH `/api/invoices/{id}`

Correct extracted fields (e.g. supplier, invoice number, dates, amounts, currency, line
items). Corrections are audited and distinguished from extracted/raw values.

```json
{ "invoice_number": "INV-2026-001", "total_amount": "1240.00", "currency": "EUR" }
```

### GET `/api/invoices/{id}/validations`

Returns validation results grouped by the latest `run_id`, each with rule name, severity,
pass/fail and details.

### GET `/api/invoices/{id}/duplicates`

Returns duplicate candidates with match type (`exact_file`, `business`, `fuzzy`), score and
signals. Duplicates are flagged, never silently discarded.

### GET `/api/invoices/{id}/anomalies`

Returns the anomaly score, model version, flag and human-readable explanation signals.

### GET `/api/invoices/{id}/purchase-order`

Returns PO match results: matched supplier/items, quantity/price mismatches.

---

## Approvals

### GET `/api/approvals`

Returns the current user's approval queue (tenant-scoped, permission- and policy-filtered).

### POST `/api/approvals/{id}/decision`

```json
{ "decision": "APPROVE", "comments": "Matches PO-4471" }
```

- Decision is `APPROVE`, `REJECT` or `REQUEST_CORRECTION`.
- Server enforces permission, current state and policy limits.
- Invalid or unauthorized transitions fail (`403`/`409`) and are audited.
- Successful decisions create an audit event and may trigger notifications.

---

## Audit and analytics

> **Implemented:** `GET /api/audit` returns `{items, total, limit, offset}` (newest
> first) for the active tenant; requires `audit:read` (auditor/admin).

### GET `/api/audit-logs`

Filter by `entity_type`, `entity_id`, `actor_id`, `date_from`, `date_to`. Auditor role or
equivalent permission required; tenant-scoped.

### GET `/api/analytics/summary`

Dashboard metrics: document counts, pending approvals, review queue size, duplicate/anomaly
flags, average processing time and workflow bottlenecks. Totals always match the
underlying authorized (tenant-scoped) records.

---

## Status and error codes

| Code | Meaning |
| --- | --- |
| 200 | Success |
| 202 | Accepted (processing queued) |
| 400 | Invalid request/file |
| 401 | Missing or invalid credentials |
| 403 | Authenticated but not permitted (or cross-tenant access) |
| 404 | Not found in the caller's tenant |
| 409 | Conflict (duplicate, state conflict, job already running) |
| 413 | Payload too large |
| 422 | Schema validation error |
| 429 | Rate/usage limit |
| 500 | Unexpected server error (no sensitive detail) |

> Cross-tenant access attempts return `404` or `403` and are audited. See
> [`security.md`](security.md).
