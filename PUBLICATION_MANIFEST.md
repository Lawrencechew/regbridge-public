# Publication manifest

## Edition

- Project: RegBridge — Regulatory Workflow Platform
- Edition: Public Portfolio Edition
- Publication source: this repository only
- History model: fresh public Git history; no private repository history inherited
- Domain content: synthetic only

## Included

- React/Vite frontend
- FastAPI backend and Alembic migrations
- PostgreSQL persistence architecture
- OIDC/PKCE authentication and server-side sessions
- Organisation-scoped RBAC and tenant isolation
- Deterministic validation, reconciliation, orchestration, and artifact generation
- Synthetic `example-compliance` RegPack and example data
- Docker/Compose definitions, public CI, tests, and security documentation

## Excluded

- Private Git history
- Private or regulator-specific RegPacks
- Real regulator datasets, source documents, and templates
- Credentials, private configuration, production identifiers, logs, runtime databases, generated customer artifacts, and private test evidence
- Commercial or employer-confidential material

## Synthetic-content statement

`example-compliance` is fictional and has no regulator affiliation or legal authority. Names, records, rules, sources, and output templates included with it exist only to demonstrate the reusable engineering architecture.

## Verification

Before initial publication, the owner completed the manual ownership/IP provenance review and approved the sanitized tree. Automated checks covered backend and frontend tests, linting, production builds, dependency auditing, secret scanning, container scanning, migration startup, and the synthetic end-to-end workflow.

Copyright © Lawrence Chew. All rights reserved. See `README.md` and `THIRD_PARTY_NOTICES.md` for the publication and third-party terms.
