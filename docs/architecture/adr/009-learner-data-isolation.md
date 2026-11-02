# ADR-009: Learner data isolation and ownership

- **Status:** Accepted
- **Date:** 2026-10-27
- **Supersedes:** -
- **Decision owner:** Member 3 (Backend & Data) with Member 2 (AI & RAG)
- **Related requirements:** INV-AUTH-001, INV-SEC-002, INV-SEC-001, FR-AUTH-001, FR-PROF-001
- **Related artifacts:** `docs/architecture/invariants.md` INV-AUTH-001, `permission-model.md`, `runtime-policy-catalog.md`, `structural-constraints.md` S6
- **Review triggers:** any cross-user read or write; a record query not scoped to the authenticated user; a file-upload route appearing; `cross_user_exposure_total > 0`.

## Context

Every learner record - profile, sessions, vocabulary state, writing submissions, progress - is personal data. The platform's trust claim depends on one learner never reading or writing another learner's data, through any request path, including negative and error paths.

The identity used to scope every query must come from the authenticated session, never from a client-supplied field. The runtime must also expose no file-upload surface that could ingest arbitrary personal files.

## Decision

Make learner-data isolation a first-class, statically and behaviorally enforceable boundary:

- The principal is derived only from the authenticated session; no request payload may set a `user_id` (`INV-AUTH-001`).
- Every session, progress, vocabulary, and profile query is scoped to the authenticated user id; a foreign id yields HTTP 403/404 with zero record disclosure and zero state mutation (`INV-AUTH-001`).
- The application exposes zero file-upload endpoints; route introspection must confirm none accept `multipart/form-data` or file payloads (`INV-SEC-002`).
- Runtime database access to learner data is owner-scoped; there is no query path that returns another user's rows.

This is enforced both by a negative test suite (cross-user probes) and by the single-writer / owner-scoped repository rules in `structural-constraints.md` S6.

## Ownership boundaries

| Data | Owner (writer) | Allowed reader | Forbidden |
|---|---|---|---|
| `users`, `profiles` | `AuthSecurity` | the owning learner | any other learner; any non-owner admin path |
| `sessions`, `messages` | `ChatRouter` | the owning learner | any cross-user read |
| `user_vocabulary` | `VocabularyService` | the owning learner | any cross-user read |
| `writing_submissions` | `GrammarEvaluator` | the owning learner | any cross-user read; the corpus |
| `learning_events` | `ProgressService` | `ProgressService` projection for the owner | cross-user aggregation surfaced to a learner |

No two elements share a write path; a read that crosses an ownership boundary is a finding, not a convenience.

## Rationale

- Deriving the principal only from the session removes the identity-spoofing class of bug: a payload field cannot change whose data is read.
- Owner-scoping every repository call makes cross-user exposure testable at a single boundary with a fixed probe suite.
- A zero-upload posture removes an entire attack surface (arbitrary file ingestion) rather than mitigating it.
- Stating the rule as an invariant plus a static import/single-writer rule means it is enforced by architecture, not by a reviewer's promise.

## Alternatives considered

| Option | Failed criterion | Evidence |
|---|---|---|
| Trust a `user_id` field in the request | Isolation/authority: the client is untrusted; a forged id becomes an access grant | `INV-AUTH-001` |
| Rely on frontend filtering only | Enforcement: the API is the boundary; a direct API call bypasses any UI check | `INV-AUTH-001` |
| Support file uploads with scanning | Attack surface / scope: R1 excludes uploads; scanning is out of scope | `INV-SEC-002` |
| Public or shareable sessions | Isolation: session sharing violates owner-scoping | `INV-AUTH-001` |

## Responsibility map

| Element | Responsibility | Implemented in |
|---|---|---|
| `AuthSecurity` | Session identity, principal derivation, per-record authorization | `src/backend/auth/security.py` |
| `ProfileSchema` | Language and CEFR validation on profile payloads | `src/backend/api/schemas/profile.py` |
| `AppEntry` | Composition root; registers no upload routes | `src/backend/main.py` |
| record services (`ChatRouter`, `VocabularyService`, `ProgressService`, `GrammarEvaluator`) | Issue owner-scoped queries only | `src/backend/**` |

## Quality attribute tradeoffs

| Attribute | Tactic | Buys | Costs | Metric that would invalidate |
|---|---|---|---|---|
| Security / isolation | Principal from session only; owner-scoped repos; 404 on foreign id | Cross-user exposure testable at one boundary | An extra authorization check per access | `cross_user_exposure_total > 0` |
| Scope control | No upload endpoints | Removes arbitrary-file attack surface | No document upload feature in R1 | any upload route exposed |
| Testability | Fixed cross-user probe suite | Regression is detectable | Probe maintenance | a probe passes on a broken build |

## Consequences

**Benefits**

- Cross-user exposure is a testable predicate, not a claim.
- Identity spoofing via payload is structurally impossible.
- The zero-upload posture is verifiable by route introspection.

**Costs**

- An authorization check is paid on every record access.
- No collaborative or shared-session features in R1.
- Learners cannot upload personal documents.

## Review triggers

| Trigger | Threshold | Action |
|---|---|---|
| Cross-user exposure | any occurrence | Block release; security incident; add a probe |
| Upload route appears | any occurrence | Treat as INV-SEC-002 failure; remove the route |
| Payload-supplied identity accepted | any occurrence | Treat as INV-AUTH-001 failure; block release |

## Change log

| Date | Change | Evidence |
|---|---|---|
| 2026-10-27 | Initial decision accepted at baseline R1 | `evaluation-logbook.md` 2026-10-27 |
| 2026-11-02 | Rescoped to learner-data isolation (INV-AUTH-001); memory/checkpoint/summary/redaction/retention content removed as not SSOT-backed | This consolidation; `trace-matrix.md` INV-AUTH-001 / INV-SEC-002 rows |
