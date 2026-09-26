# RegBridge architecture

```text
Browser -> React/Vite frontend -> FastAPI API -> RegFlow orchestration
                                           -> deterministic RegPack evaluation
                                           -> PostgreSQL state and audit records
                                           -> transient generated artifact bytes
```

The browser guides selection, upload, mapping review, preflight, output download, and
history inspection. FastAPI is authoritative for authentication, authorization,
mapping, evaluation, transitions, and output generation. PostgreSQL stores workflow
and security metadata; source bytes, canonical rows, detailed findings, runtime
declarations, and generated workbook bytes are intentionally transient.

## Responsibility boundaries

- **RegBridge** owns the API, identity, tenant isolation, sessions, persistence, safe
  errors, configuration, and deployment boundary.
- **RegFlow** owns the explicit state machine and orchestration from source evidence to
  persisted decision and artifact metadata.
- **RegPack** owns a versioned evidence module: provenance, canonical schema,
  workflow sections, deterministic rules, synthetic fixtures, and output template.

RegPacks contain no arbitrary executable expressions. Generic engines load validated
definitions and produce repeatable findings; an LLM is not part of decision-making.

## Persisted concepts

- Users and external identities link an OIDC subject to a local account.
- Organisations, memberships, roles, and invitations define tenant access.
- RegFlow runs retain state, revision, pack fingerprint, and privacy-minimal source
  metadata.
- Mapping profiles and immutable snapshots record reviewed transformations;
  schema/header signatures prevent stale reuse.
- Preflight snapshots retain decision counts and fingerprints, not source rows or
  full findings.
- Artifact metadata retains filename, size, SHA-256, and definition/dataset identity;
  workbook bytes are returned once.
- Audit records capture lifecycle changes and request correlation.
- Tenant-scoped idempotency records bind a key to request fingerprints and outcomes.

Alembic owns a linear PostgreSQL migration history. The container entrypoint upgrades
to `head` before Uvicorn starts. The public demo pack is synthetic and is not a
statement of regulatory policy.
