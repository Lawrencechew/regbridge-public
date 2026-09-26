# RegBridge

**Public Portfolio Edition**

RegBridge is an engineering reference implementation for deterministic regulatory evidence workflows.

It explores how structured regulatory workflows can be modelled as secure, auditable and repeatable software processes while keeping domain-specific regulatory logic isolated from the reusable workflow engine.

This repository contains the public portfolio edition of RegBridge. It uses synthetic data and a fictional Example Compliance Pack. Private domain-specific content, production data and development history are intentionally excluded. RegBridge is an independent engineering reference implementation with no regulator affiliation or endorsement.

> This portfolio edition is not production software, legal advice, a compliance certification, or a regulatory submission service. Its bundled RegPack and data are deliberately synthetic.

## Why RegBridge exists

Evidence and compliance workflows often rely on spreadsheets, manual mappings, repeated validation, inconsistent processing, and limited traceability. RegBridge demonstrates a controlled path:

```text
source data -> mapping -> validation/preflight -> deterministic processing
            -> artifact generation -> audit trail
```

## What is implemented

- React and Vite browser application with an explicit staged RegFlow.
- FastAPI API with validated CSV/XLSX ingestion and bounded processing.
- PostgreSQL persistence and Alembic migrations.
- Provider-agnostic OIDC authorization-code login with PKCE.
- Opaque, hashed server-side sessions, CSRF protection, and secure-cookie controls.
- Organisation-scoped `OWNER`/`MEMBER` RBAC and tenant-scoped repositories.
- Idempotency keys, optimistic run revisions, fingerprints, and audit records.
- Declarative, versioned RegPacks with deterministic validation and reconciliation.
- Template-based XLSX artifact generation.
- Structured safe logging, low-cardinality metrics, readiness/liveness checks, and hardened reference containers.

The reusable application and workflow engines are real. The public domain content is the synthetic **Example Compliance Pack**; no private or regulator-specific packs are included.

## Architecture

```text
Browser / React
      |
      | credentialed HTTP + CSRF header
      v
FastAPI API (authentication, tenant boundary, orchestration)
      |                 |
      |                 +--> RegPack validation/reconciliation/output
      v
PostgreSQL (sessions, organisations, workflow metadata, audit trail)
```

Uploaded bytes, canonical row values, detailed findings, runtime declarations, and generated workbook bytes are processed transiently. PostgreSQL retains privacy-minimal workflow metadata, reviewed mapping snapshots, result fingerprints, artifact metadata, idempotency records, and audit events.

See [the architecture](docs/architecture.md) and [security model](docs/security-model.md).

## RegPacks

A RegPack is a versioned declarative module containing provenance, a canonical schema, validation rules, reconciliation rules, and optionally an output template. Application code contains no regulator-specific branches and rules cannot execute arbitrary expressions.

The included `example-compliance` pack is fictional. It demonstrates versioned discovery and content fingerprinting, CSV-to-canonical mapping, required-field and range checks, deterministic reconciliation, preflight, and generation of a synthetic XLSX evidence report.

## Local development

Prerequisites: Docker with Compose. Optional native development uses Python 3.13, [uv](https://docs.astral.sh/uv/), Node.js 22+, and npm.

```bash
cp .env.example .env
docker compose up --build
```

On PowerShell, use `Copy-Item .env.example .env` instead of `cp`.

Local URLs:

- Frontend: <http://localhost:5180>
- API: <http://localhost:8000>
- OpenAPI: <http://localhost:8000/docs>
- Readiness: <http://localhost:8000/api/v1/ready>

The documented development configuration uses the application's existing unauthenticated local mode. It is not an authentication bypass: production configuration rejects `AUTH_ENABLED=false` and unsafe defaults.

## Synthetic demo

1. Start the Compose stack.
2. Open the frontend and select **Example Compliance Pack** version `1.0.0`.
3. Upload `examples/example-evidence.csv`.
4. Confirm the recommended source-to-canonical mappings.
5. Run preflight and inspect the deterministic validation/reconciliation result.
6. Generate and download the synthetic evidence report.
7. Inspect the run, artifact metadata, revisions, and audit activity.

The sample organisation and identities used in documentation are `Northstar Compliance Labs`, `alice@example.test`, and `bob@example.test`.

## Configuration

`.env.example` contains development-only defaults and obvious OIDC placeholders. Do not commit `.env`, credentials, tokens, certificates, production endpoints, or populated identity-provider values. Production mode requires explicit HTTPS, PostgreSQL, authentication, cookie, host, origin, proxy, and secret settings.

Microsoft Entra and other standards-compliant OIDC providers can be configured through `OIDC_ISSUER`, `OIDC_DISCOVERY_URL`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, and `OIDC_REDIRECT_URI`. No tenant or client identifier is bundled.

## Tests

```bash
cd backend
uv sync --frozen
uv run pytest

cd ../frontend
npm ci
npm test
npm run lint
npm run build
```

Public CI runs the backend and frontend checks, scans committed content for secrets, and builds and scans both containers. Development-machine results are not represented as universal production capacity.

## Security and limitations

Security controls are described in [SECURITY.md](SECURITY.md). The design includes tenant predicates, membership revalidation, CSRF, PKCE, session rotation, bounded imports, formula-injection defenses, safe errors, fail-closed production checks, and non-root/read-only production containers.

Important limitations:

- The synthetic pack is illustrative and has no regulatory authority.
- Generated artifacts require human review.
- Single-host Compose is a reference topology, not a scalability recommendation.
- In-process rate limiting is not a substitute for a distributed edge control.
- The project has not been certified against a compliance or security standard.
- A real deployment requires an independently configured identity provider, TLS ingress, secrets management, monitoring, backups, and operational review.

## Project status

Portfolio/reference edition. The reusable architecture is implemented and tested; publication does not imply production support or fitness for a particular regulatory purpose.

## Copyright and use

Copyright © Lawrence Chew. All rights reserved.

Source code is published for portfolio and evaluation purposes. No licence is granted for redistribution, modification or commercial use unless explicitly stated otherwise. Third-party dependencies remain subject to their own licences; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
