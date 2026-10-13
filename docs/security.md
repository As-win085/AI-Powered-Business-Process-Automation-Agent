# Security, Isolation and Privacy

> AI-Powered Business Process Automation Agent — Version 1.0 · October 2026

This document defines the security model, tenant isolation controls and privacy policy.
It is the reference for implementing and testing protection of tenant-owned data.

> **Foundational rule:** multi-tenancy, data isolation and auditability are foundational
> requirements, not features to bolt on later.

---

## 1. Security objectives

| Objective | Description |
| --- | --- |
| Tenant isolation | Tenant A can never read, modify or infer Tenant B's business data, files or analytics |
| Authentication integrity | Only verified identities with valid credentials hold a session |
| Authorization correctness | Every action is permitted by role/permission and current state |
| Data integrity | Monetary math is decimal; state changes are transactional; audit history is protected |
| Confidentiality | Secrets and sensitive invoice contents are never logged or committed |
| Traceability | Important changes can be reconstructed (who, what, when, why) |
| Privacy | Retention, deletion and third-party sharing are documented and enforced |

---

## 2. Authentication

- Users authenticate with email + password.
- Passwords are hashed with a modern algorithm (e.g. Argon2 via `pwdlib`); never stored
  or logged in plaintext.
- Sessions use short-lived JWT access tokens (signed, verified on every request); refresh
  handling follows current best practice.
- Invalid, expired or tampered tokens are rejected with `401`.
- Login failures, lockouts and credential changes are audited.
- MFA is a future enhancement, not required for v1.

Requirements for cookie/token storage and signing keys are documented in `.env.example`;
rotate secrets via environment or a secrets manager, never in code.

---

## 3. Authorization and roles

Permissions are enforced **on the backend**. Hiding a button in React does not secure an
endpoint.

| Role | Scope |
| --- | --- |
| Admin | Manage users, roles, tenant settings, supplier master data |
| Finance employee | Upload and correct documents, run processing, view validation/duplicates |
| Approver | Make approval decisions within policy limits |
| Auditor | Read permitted history; no state changes |

Rules:

- Roles are tenant-scoped (a user may hold different roles in different tenants).
- Every service call checks permission **and** tenant membership.
- Authorization does not rely on client-supplied role or tenant values.
- Unauthorized approval attempts fail server-side and are audited.

---

## 4. Tenant isolation (enforced at every layer)

```
Authenticated user
   └─► Membership lookup (user_id + tenant_id)  ← single source of tenant truth
         └─► TenantContext(tenant_id, actor_id, roles, permissions)
               └─► Service requires TenantContext
                     └─► Repository: WHERE tenant_id = :ctx AND id = :id
                           └─► Database: non-null tenant_id + composite FKs
```

| Layer | Control |
| --- | --- |
| Context | Active tenant derived from a valid membership; browser `tenant_id` is never trusted alone |
| Service | Tenant context is a required parameter; no data access without it |
| Repository | Reads/updates/deletes filter by both record id and tenant id |
| Database | Non-null `tenant_id`; composite FKs; tenant-scoped unique constraints; tenant-prefixed indexes |
| Cache | Tenant-scoped cache keys |
| Files | Tenant-prefixed storage paths resolved only through authorized backend operations |
| Workers | Tenant context carried in job payloads and revalidated before processing |
| Analytics | Aggregations are always tenant-scoped |
| ML | One tenant's history is never used to score another tenant's model unless a separately designed, consented shared-model policy permits it |
| Optional | PostgreSQL row-level security as defense in depth after application-level controls work |

### 4.1 Composite foreign keys

Composite FKs (`(tenant_id, child_id) → parent(tenant_id, id)`) make cross-tenant
relationships impossible at the database level. See
[`database.md`](database.md#41-composite-foreign-key-pattern).

### 4.2 Cross-tenant isolation tests

Isolation tests are **mandatory for every major resource**. A standard fixture creates
two tenants, a user and a record in each, then asserts:

- Tenant A cannot `GET`/`PATCH`/`DELETE` Tenant B's record (expect `404` or `403`).
- Lists return only the caller's tenant records.
- A forged `tenant_id` in the request body/header cannot switch tenants.
- Background jobs with a mismatched tenant context are rejected before side effects.
- File downloads for another tenant fail.

Milestone 1 gate: tests prove Tenant A cannot read or modify Tenant B's records.

---

## 5. File upload and storage security

Private storage lives **outside the public frontend**:

```
storage/tenants/<tenant-id>/documents/<document-id>/original.pdf
```

The directory structure is organizational, **not** a security boundary. Required
controls:

- **Server-side identifiers:** never trust user-provided paths or filenames.
- **Validation:** check size, extension, declared MIME type **and** file signature
  (magic bytes). Reject mismatches.
- **Path traversal:** reject `..`, absolute paths, symlinks and encoded traversal.
- **Supported formats:** allow-list (e.g. PDF, PNG, JPEG); reject everything else.
- **Authorization:** downloads/previews require tenant membership + permission.
- **Integrity:** store a cryptographic hash (SHA-256) for integrity and exact-file
  duplicate detection.
- **Exclusion:** uploaded files are never committed to Git or baked into container images
  (mount `storage/` as a local volume).
- **Backup/deletion:** documented and implemented (see §7).
- **Abstraction:** a storage interface allows swapping local storage for private
  S3-compatible storage.
- **Serving:** files are streamed through authorized backend endpoints; the storage
  directory is not statically served.

---

## 6. AI/LLM security and privacy

- Provider credentials live in environment variables or a secrets manager.
- Requests enforce timeouts, bounded retries and usage limits.
- Provider output is **untrusted data**: always validated with Pydantic; never executed.
- **Prompt injection:** instructions found inside invoice text are treated as data and
  ignored. The model cannot change tenant identity, permissions or approval authority.
- Only the minimum necessary content is sent to a provider.
- Do not send files or extracted content until the provider's privacy and retention terms
  are understood and documented.
- A manual-review fallback exists when the provider is unavailable.
- Persist provider/model identifiers and extraction-schema versions for traceability.
- Do not send secrets, unrelated tenant data or user PII beyond what extraction requires.

---

## 7. Data retention, deletion and privacy

| Policy | Description |
| --- | --- |
| Retention | Define per-tenant retention for documents, extracted text, audit logs and job records |
| Deletion | Deleting a document removes its file, text, derived records as configured, and writes an audit event |
| Right to erasure | Support removing a user's personal data subject to audit/legal retention requirements |
| Third-party sharing | Document every external processor (LLM, email) and the data categories shared |
| Backups | Document backup location, frequency and restoration; backups remain tenant-isolated |
| Logging | Never log passwords, tokens, secrets or full invoice contents |
| Dev data | Use synthetic or appropriately licensed data; never commit real invoices |

Retention/deletion behaviour must be documented **and** tested.

---

## 8. Audit logging

- Record an audit event for every important change: uploads, extraction runs, corrections,
  validation overrides, duplicate resolutions, state transitions and approval decisions.
- Each event stores: actor, tenant, entity type/id, action, change summary, timestamp.
- Audit history is **append-only** and protected from unauthorized modification.
- Auditors can reconstruct who changed what, when and why.
- Audit reads are themselves tenant-scoped and permissioned.

---

## 9. Secrets and configuration

- All secrets (DB URL/password, JWT keys, provider keys, SMTP credentials) come from
  environment variables or a secrets manager.
- `.env` is git-ignored; `.env.example` contains only placeholders.
- Never print secrets in logs, errors or API responses.
- Rotate keys on exposure; different secrets per environment.

---

## 10. Threat model (STRIDE-lite)

| Threat | Example | Mitigation |
| --- | --- | --- |
| Spoofing | Forged JWT or forged `tenant_id` | Verify signatures; derive tenant from membership, not request |
| Tampering | Editing another tenant's invoice | Tenant-scoped queries + composite FKs + permissions |
| Repudiation | Denying an approval | Append-only audit events with actor + timestamp |
| Information disclosure | Cross-tenant read; leaked file path | Isolation at every layer; authorized streaming; no static serving |
| Denial of service | Huge uploads; provider abuse | Size limits; rate/usage limits; bounded retries/timeouts |
| Elevation of privilege | Worker approving invoices | State machine + role checks; workers cannot approve |
| Injection (prompt) | Malicious text in PDF | Treat output as untrusted; ignore embedded instructions |
| Insecure file upload | Malicious/executable upload | Signature + MIME + extension checks; allow-list; non-executable storage |

---

## 11. Security testing checklist

- [ ] Cross-tenant reads/writes denied for every major resource.
- [ ] Forged `tenant_id` cannot switch tenants.
- [ ] Unauthenticated and expired-token requests rejected.
- [ ] Role-based access enforced (finance cannot approve; auditor cannot mutate).
- [ ] Unauthorized approval / invalid state transitions fail.
- [ ] Invalid, oversized and path-traversal uploads rejected.
- [ ] File downloads restricted to authorized tenant members.
- [ ] Secrets never appear in logs, errors or responses.
- [ ] Prompt-injection content does not alter permissions or state.
- [ ] Retried jobs do not duplicate business records.

---

## 12. Responsive disclosure

For a portfolio deployment, document the environment as **demonstration data only**.
Do not process real financial documents, and state clearly that the system is not a
production payment or fraud-detection tool.
