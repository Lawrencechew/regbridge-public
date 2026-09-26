# RegBridge engineering portfolio

## Problem

Evidence workflows combine unstable operational exports, prescribed schemas,
period-specific policy, reconciliation, fixed templates, provenance, and human
accountability. A successful file is insufficient: reviewers need to know which
source, mapping, rules, and version produced it.

## Architecture decisions

RegBridge separates the secure product boundary from RegFlow orchestration and
versioned RegPacks. Regulatory checks are declarative and deterministic, so identical
canonical input and pack versions produce repeatable decisions. Recommendations help
users map data, but ambiguous matches remain unresolved and users confirm mappings.

Generic engines avoid regulator branches in application code. The public
`example-compliance` pack demonstrates a single-dataset workflow using fictional
rules and data; private domain packs are not included in this edition.

## Persistence model

PostgreSQL stores optimistic run revisions, pack/source fingerprints, reviewed
mapping snapshots, reusable profile versions, decision summaries, artifact hashes,
idempotency records, and audit events. This enables resume, stale-state detection,
replay safety, and explainability while excluding source rows, full findings, runtime
declarations, and generated workbook bytes.

## Security engineering

OIDC code flow with PKCE keeps provider tokens server-side. Opaque sessions, CSRF,
role checks, final-owner protection, and organisation predicates defend the tenant
surface. Production rejects unsafe defaults, and external failures do not expose
stack traces, SQL, paths, tokens, or session identifiers.

## Production engineering

The reference deployment includes Alembic startup migrations, PostgreSQL readiness,
separate liveness/readiness, correlated JSON logs, bounded metrics, backup/restore
drills, non-root containers, read-only filesystems, tmpfs, and Docker Scout gates.

## Challenges solved

- deterministic evaluation with source-traceable RegPack versions;
- stale mapping prevention using schema and source-layout signatures;
- idempotent workflow execution and optimistic concurrency;
- strict tenant isolation across persisted resource types;
- evidence, decision, dataset, and output fingerprinting;
- secure OIDC sessions without frontend bearer tokens; and
- hardened Compose deployment with diagnosable startup and recovery.
