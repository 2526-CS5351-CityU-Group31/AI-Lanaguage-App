# ADR-008: Adopt event-sourced learning records and server-side deterministic scoring

- **Status:** Accepted
- **Date:** 2026-10-27
- **Supersedes:** -
- **Decision owner:** Member 3 (Backend & Data)
- **Related requirements:** REQ-LANG-FR-007, REQ-LANG-FR-008, REQ-LANG-INV-004, REQ-LANG-INV-005, REQ-LANG-FR-005, REQ-LANG-FR-006
- **Related artifacts:** `docs/architecture/invariants.md` INV-004/005, `memory-design.md`, `runtime-policy-catalog.md` RP-012/RP-013, `structural-constraints.md` S6, `mcp-tool-manifest.md`
- **Review triggers:** `progress_total_mismatch_count > 0`; `client_score_acceptance_count > 0`; dashboard projection p95 `> 1 s`; `learning_events` volume `> 1,000,000` rows/month; a scoring rule or rubric change; a request to store a model-computed total.

## Context

Learners see three kinds of numbers: session and word counts, quiz results, and recent topics. Each is a claim about what happened. If the number is written by a model, it is a narrative; if it is written by the UI, it is forgeable; if it is a denormalised counter, it drifts from the events that justify it.

The project also needs a defensible answer to "how do you know the progress is real?" for the demo and the report. A stored event with an actor, a timestamp and a reference is evidence; a counter is not.

## Decision

Store every learning fact as an immutable row in `learning_events`, and compute dashboard totals and quiz aggregates as read-time projections over those events. Quiz answer keys live only on the server; the scoring function is deterministic and versioned; an attempt is immutable and a regrade is a new event.

No model may write a score or a progress total. No client-supplied score is accepted.

## Event model

| Event type | Payload (minimal) | Emitted by | Idempotency key |
|---|---|---|---|
| `session_started` | `session_id`, topic, level | `PracticeSessionService` | `(user_id, request_id)` |
| `turn_completed` | `session_id`, `turn_id`, outcome, `validation_id` | `PracticeSessionService` | `(user_id, turn_id)` |
| `writing_submitted` | `submission_id`, word_count | `WritingFeedbackService` | `(user_id, request_id)` |
| `suggestion_decided` | `submission_id`, decision | `WritingFeedbackService` | `(user_id, submission_id)` |
| `vocabulary_confirmed` | `word`, `sense`, level | `VocabularyService` | `(user_id, word, sense)` |
| `vocabulary_reviewed` | `vocabulary_id`, state | `VocabularyService` | `(user_id, vocabulary_id, state)` |
| `quiz_scored` | `quiz_id`, `attempt_id`, score, rubric_version | `AssessmentService` | `(user_id, attempt_id)` |
| `content_retired` | `source_id`, `version_id` | `ContentPublisher` | `(source_id, version_id)` |

Rules:

- `learning_events` is append-only. There is no update or delete endpoint; a correction is a new event with `corrects_event_id`.
- The event carries a reference (`session_id`, `attempt_id`), not raw learner text. Raw text stays in its owner-scoped table.
- Every mutating request carries a client `request_id`; the unique key makes a retry idempotent (`RP-012`).
- A failed write rolls back the business mutation; a turn is not displayed if its event did not commit.

## Scoring rules

- Quiz items are validated and stored with `correct_index` in a server-only table. The client receives items and options only.
- `AssessmentService.score_attempt()` loads the stored key, compares the submitted option ids, and writes a score with `rubric_version` and `scorer="server"`.
- A client field named `score` is ignored, logged and counted; it never reaches the database (`INV-004`).
- An attempt is immutable. A regrade creates a new event with `regrades_attempt_id` and a reason; the old attempt remains visible in audit.
- Dashboard totals are a pure function of events: `sessions = count(session_started)`, `words_reviewed = count(vocabulary_reviewed)`, `quiz_accuracy = sum(quiz_scored.score) / count(quiz_scored)`, `recent_topics = distinct(turn_completed.topic)` over the last 30 days.
- A projection cache is permitted only if it is checked against the event aggregate in the same request; a mismatch hides the dashboard and raises CRITICAL (`RP-013`).

## Rationale

- Events are the smallest honest unit: they record what happened, when, for which owner and under which validation id.
- Read-time projection removes the drift class of bug entirely; the dashboard cannot disagree with its source because there is no second source.
- A server-held key is the only way to make a quiz score authoritative; sending the key to the client makes every score forgeable.
- An immutable attempt plus a correction event gives a real audit trail without rewriting history.
- The design makes the "totals agree with stored events" acceptance example a testable predicate, not a demo script.

## Alternatives considered

| Option | Failed criterion | Evidence |
|---|---|---|
| Denormalised counters updated in place | Invariant protection: a lost update or double retry silently drifts the total; no source of truth to repair from | `INV-005`, `evaluation-table.md` C1 record dimension |
| Model-generated progress summary | Authority separation: a narrative is not a record; it cannot be audited or recomputed | `FR-008`, `INV-005` |
| Client-computed score submitted with the attempt | Isolation/authority: the client is untrusted; a forged score becomes a learning record | `INV-004`, RP-014 |
| Answer key returned with the quiz for "instant feedback" | Authority: the key is exposed before submission and the score becomes advisory | `FR-007`, `INV-004` |
| Event log in the model prompt to "personalise" | Privacy and isolation: raw events and learner text leave the database for a provider call without a need | `SEC-004`, `INV-011` |

## Responsibility map

| Element | Responsibility | Implemented in |
|---|---|---|
| `ProgressLedger` | Append events, project totals, parity check | `src/progress_ledger.py` |
| `AssessmentService` | Validate items, hold keys, score deterministically | `src/assessment_service.py` |
| `PracticeSessionService` | Emit session/turn events in the same transaction as the turn | `src/practice_session_service.py` |
| `WritingFeedbackService` | Emit submission/decision events | `src/writing_feedback_service.py` |
| `VocabularyService` | Emit confirmation/review events with dedupe key | `src/vocabulary_service.py` |
| `ObservabilityStore` | Record scoring mismatches and parity failures as security events | `src/observability_store.py` |

## Quality attribute tradeoffs

| Attribute | Tactic | Buys | Costs | Metric that would invalidate |
|---|---|---|---|---|
| Integrity | Append-only events, read-time projection | Totals provably match events | Aggregation query per dashboard read | `progress_total_mismatch_count > 0` |
| Security | Server-held keys, client score ignored | Scores cannot be forged | Key storage and access control | `client_score_acceptance_count > 0` |
| Auditability | Immutable attempts, correction events | History is defensible | More rows and a correction UI | regrade without an event |
| Performance | Index on `(user_id, occurred_at)`, projection cache with parity | Fast dashboard at small volume | Parity check adds a query | dashboard p95 > 1 s |
| Modifiability | Versioned rubric and scorer | Scoring changes are attributable | Old attempts need a rubric reference | score without `rubric_version` |
| Cost | No model call for totals | Deterministic and cheap | None material | model-sourced total found |

## Consequences

**Benefits**

- The dashboard is a query, not a state machine; bugs are localised to projection logic.
- Quiz scoring is provable and replayable from stored attempts.
- Cross-user tests can assert on events as well as responses.
- The same events feed the evaluation logbook's usage and quality narratives.

**Costs**

- More rows than counters; retention and indexing matter at volume.
- A correction UI is needed for regrades and mis-scored attempts.
- The projection query must be tuned; a naive aggregate can be slow.
- Event schema changes need versioning.

## Review triggers

| Trigger | Threshold | Action |
|---|---|---|
| Parity mismatch | any occurrence | Hide dashboard, recompute, CRITICAL, open a bug diary entry |
| Client score accepted | any occurrence | Treat as INV-004 failure; block release |
| Event volume | > 1M/month | Add monthly partitions; benchmark projections |
| Dashboard p95 | > 1 s | Add a cached projection with parity check |
| Scoring rule change | proposed | New rubric version + re-score fixtures + ADR |

## Change log

| Date | Change | Evidence |
|---|---|---|
| 2026-10-27 | Initial record model accepted at baseline R1 | `evaluation-logbook.md` 2026-10-27; `trace-matrix.md` rows REQ-LANG-FR-008, REQ-LANG-INV-005 |
