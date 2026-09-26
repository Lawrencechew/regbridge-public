# Security model summary

| Threat | Implemented mitigation |
|---|---|
| Cross-tenant data access / IDOR | Request tenant context, membership revalidation, organisation-scoped repositories, generic not-found behavior, tenant isolation tests |
| Session theft or fixation | Random opaque sessions, server-side HMAC digests, rotation at login, expiry/revocation, HttpOnly/Secure/SameSite cookies |
| CSRF | Session-bound double-submit token and required header on unsafe protected requests |
| OIDC replay or substitution | PKCE S256, single-use state, nonce, exact issuer/audience/`azp`, signed JWKS and time-claim validation |
| Stale mappings | RegPack/schema versions, pack fingerprints, source header signatures, mapping fingerprints, and explicit invalidation |
| Duplicate/replayed submissions | Organisation-scoped idempotency keys bound to request fingerprints and atomic run revisions |
| Tampered or mismatched outputs | Dataset, RegPack, output-definition, report, and artifact SHA-256 fingerprints persisted with audit history |
| Dependency vulnerabilities | Locked backend and frontend inputs plus public CI dependency and container scanning gates |
| Privileged container compromise | Dedicated non-root users, read-only production filesystems, bounded tmpfs, minimal images, loopback frontend publication |
| Sensitive error/log disclosure | Stable external error envelopes and allowlisted structured log fields; access/query logging is suppressed around OIDC codes |

RegBridge does not protect against a compromised host, identity provider, authorised
malicious owner, vulnerable browser, or incorrect RegPack policy definition.
Generated outputs require human review. This summary describes implemented controls,
not an independent audit or certification.
