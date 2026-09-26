# Security policy

## Scope

This repository is a portfolio reference implementation, not a hosted service. Security reports should describe an issue in the published source without including credentials, personal data, or live exploit traffic.

## Implemented controls

- OIDC authorization-code flow with PKCE, nonce, state, issuer/audience validation, and signed JWKS validation.
- Random opaque sessions stored server-side as HMAC digests, with rotation, expiry, revocation, HttpOnly cookies, and production Secure-cookie enforcement.
- Session-bound CSRF tokens for unsafe authenticated requests.
- Organisation-scoped repositories, membership revalidation, `OWNER`/`MEMBER` checks, and generic not-found behavior across tenant boundaries.
- Input size/type/shape limits, XLSX archive limits, canonical type validation, deterministic rules, and spreadsheet-formula neutralisation.
- Idempotency keys, optimistic revisions, immutable mapping/preflight snapshots, and content fingerprints.
- Explicit CORS and host allowlists, optional trusted-proxy boundaries, CSP and other response headers, HSTS in production, rate protection, safe error envelopes, and allowlisted structured logs.
- Locked dependency inputs and non-root, read-only reference containers.

See [docs/security-model.md](docs/security-model.md) for threat boundaries and limitations.

## Secrets and deployment

No usable credentials belong in this repository. `.env.example` is a placeholder reference. Store deployed secrets in a dedicated secret-management system, rotate suspected exposures, restrict identity-provider redirects, terminate TLS at a reviewed boundary, and never reuse the local database password.

Production configuration intentionally fails closed when authentication, HTTPS, cookies, hosts, origins, database, or required secrets are unsafe.

## Reporting

Before public hosting is configured, report vulnerabilities privately to the repository owner through an agreed private channel. Do not open a public issue containing exploit details or sensitive data.

## No certification claim

The project has not been independently audited or certified and makes no claim of compliance with a security or regulatory standard.
