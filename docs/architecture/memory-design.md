# Learner data storage and isolation - baseline R1

**Purpose:** define which learner-owned stores persist, who owns each store, and how owner-scoped access is enforced.
**Owners:** Member 3 (Backend & Data); reviewed by Member 5.
**Related:** ADR-009 (learner data isolation), ADR-008 (event-sourced progress), `invariants.md` INV-AUTH-001, `structural-constraints.md` S6, `runtime-policy-catalog.md`.

> Scope note: R1 uses the SSOT registry (`docs/req/requirements.yaml`) as the single source of truth. This document covers only the stores that serve an SSOT requirement. Resumable checkpoints, durable conversation summaries, retention schedules and redaction policies have no R1 requirement and are therefore not part of this design.

## 1. Store inventory

Every learner-owned store is owner-scoped: each row carries a `user_id`, and every read/write is filtered by the authenticated principal (`INV-AUTH-001`). The runtime never returns another learner's rows.

| Store | Content | Owner (writer) | Read policy |
|---|---|---|---|
| `users`, `profiles` | Identity, language (`en`), CEFR level (A1-B2), goals | `AuthSecurity` | Owning learner only |
| `practice_sessions`, `messages` | Session metadata, learner and validated tutor turns | `ChatRouter` | Owning learner only |
| `writing_submissions` | Original learner paragraph and validated feedback | `GrammarEvaluator` | Owning learner only; never enters the corpus |
| `vocabulary`, `user_vocabulary` | Published vocabulary entries and per-user familiarity state | `VocabularyService` | Vocabulary is read-only published data; familiarity is owner-scoped |
| `learning_events` | Append-only event log (refs, type, timestamp) | `ProgressService` | Owner-scoped aggregate only; no raw text |
| `content_sources`, `content_chunks` | Reviewed curriculum text and embeddings | `IngestPipeline` (offline) | Read-only at runtime via `VectorClient` (`INV-SEC-001`) |

No two elements share a write path (single-writer rule, `structural-constraints.md` S6). A read that crosses an ownership boundary is a finding, not a convenience.

## 2. Ownership and access rule

- The principal is derived only from the authenticated session; no request payload may set a `user_id` (`INV-AUTH-001`).
- Every session, progress, vocabulary, writing and profile query is filtered by the owning user id.
- A request for a foreign record returns HTTP 403/404 with zero disclosure and zero mutation.
- The application exposes zero file-upload endpoints; there is no route that ingests arbitrary personal files (`INV-SEC-002`).
- The curriculum store (`content_*`) is separate from every learner store; learner text is never embedded, indexed, or copied into it (`INV-CITE-001` public-set check depends on this separation).

## 3. Curriculum vs learner separation

| Concern | Curriculum store | Learner stores |
|---|---|---|
| Content | Reviewed lesson text, embeddings | Turns, writing, vocabulary state, events |
| Writer | Offline `IngestPipeline` only | Owning runtime service |
| Runtime access | Read-only (`VectorClient`, `INV-SEC-001`) | Owner-scoped read/write |
| Cross-contamination | Learner text must never enter it | Curriculum text is read-only input |

This separation is what lets retrieval serve only reviewed published chunks (`INV-SCOPE-006`, `INV-CITE-001`) while learner data stays private to its owner.

## 4. Write policy

| Operation | Owner | Rule |
|---|---|---|
| Persist a validated turn | `ChatRouter` | Only after scope + validation; owner-scoped; same transaction as its event |
| Persist writing feedback | `GrammarEvaluator` | Original preserved; feedback separate; owner-scoped |
| Update vocabulary familiarity | `VocabularyService` | Owner-scoped; emits a learning event |
| Append a learning event | `ProgressService` | Append-only; owner-scoped; idempotency key |
| Ingest curriculum | `IngestPipeline` (offline) | Reviewed sources only; runtime cannot write the corpus |

## 5. Progress projection

Dashboard totals are read-time aggregates over the owner's `learning_events` and never from model output (`INV-PROG-001`). The projection is filtered by the authenticated user id; a learner never sees another learner's totals.

## 6. Done-when checks

- [x] Every store in this document serves at least one SSOT requirement.
- [x] Every learner store is owner-scoped and covered by `INV-AUTH-001`.
- [x] Curriculum and learner stores are separated; the runtime corpus is read-only (`INV-SEC-001`).
- [ ] Cross-user isolation probe suite exists and fails on a broken build (`DBT-003`).
