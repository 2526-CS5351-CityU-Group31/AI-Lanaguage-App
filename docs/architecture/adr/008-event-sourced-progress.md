# ADR-008: Event-sourced learning progress

- **Status:** Accepted
- **Date:** 2026-10-27
- **Supersedes:** -
- **Decision owner:** Member 3 (Backend & Data)
- **Related requirements:** INV-PROG-001, FR-DASH-001, FR-VOC-001, FR-VOC-002, FR-CHAT-001, FR-FEED-001, NFR-GOV-002
- **Related artifacts:** `docs/architecture/invariants.md` INV-PROG-001, `runtime-policy-catalog.md`, `structural-constraints.md` S6, `mcp-tool-manifest.md`
- **Review triggers:** `progress_mismatch_total > 0`; dashboard projection p95 `> 1 s`; `learning_events` volume `> 1,000,000` rows/month; a request to store a model-computed total.

## Context

Learners see numbers: session and word counts, recent topics, and mastered-vocabulary counts. Each is a claim about what happened. If the number is written by a model, it is a narrative; if it is written by the UI, it is forgeable; if it is a denormalised counter, it drifts from the events that justify it.

The project also needs a defensible answer to "how do you know the progress is real?" for the demo and the report. A stored event with an actor, a timestamp and a reference is evidence; a counter is not.

## Decision

Store every learning fact as an immutable row in `learning_events`, and compute dashboard totals as read-time projections over those events.

No model may write a progress total. Dashboard metrics are a deterministic aggregation over stored database events and never from LLM output (`INV-PROG-001`, `FR-DASH-001`).

## Event model

| Event type | Payload (minimal) | Emitted by | Idempotency key |
|---|---|---|---|
| `session_started` | `session_id`, topic, level | `ChatRouter` | `(user_id, request_id)` |
| `turn_completed` | `session_id`, `turn_id`, outcome, `validation_id` | `ChatRouter` | `(user_id, turn_id)` |
| `writing_submitted` | `submission_id`, word_count | `GrammarEvaluator` | `(user_id, request_id)` |
| `vocabulary_confirmed` | `word`, `sense`, level | `VocabularyService` | `(user_id, word, sense)` |
| `vocabulary_reviewed` | `vocabulary_id`, state | `VocabularyService` | `(user_id, vocabulary_id, state)` |

Rules:

- `learning_events` is append-only. There is no update or delete endpoint; a correction is a new event with `corrects_event_id`.
- The event carries a reference (`session_id`, `submission_id`), not raw learner text. Raw text stays in its owner-scoped table.
- Every mutating request carries a client `request_id`; the unique key makes a retry idempotent.
- A failed write rolls back the business mutation; a turn is not displayed if its event did not commit.

## Progress projection rules

- Dashboard totals are a pure function of events: `sessions = count(session_started)`, `words_reviewed = count(vocabulary_reviewed)`, `mastered_vocabulary = count(user_vocabulary where state='mastered')`, `recent_topics = distinct(turn_completed.topic)` over the last 30 days.
- The projection matches direct SQL `COUNT(*)` over `learning_events` (`INV-PROG-001`); any non-negative event aggregate is valid (`FR-DASH-001`).
- A projection cache is permitted only if it is checked against the event aggregate in the same request; a mismatch hides the dashboard and raises CRITICAL.

## Rationale

- Events are the smallest honest unit: they record what happened, when, for which owner and under which validation id.
- Read-time projection removes the drift class of bug entirely; the dashboard cannot disagree with its source because there is no second source.
- The design makes "totals agree with stored events" a testable predicate, not a demo script.
- Keeping raw learner text out of events keeps the log auditable without exposing writing content.

## Alternatives considered

| Option | Failed criterion | Evidence |
|---|---|---|
| Denormalised counters updated in place | Invariant protection: a lost update or double retry silently drifts the total; no source of truth to repair from | `INV-PROG-001`, `evaluation-table.md` C1 record dimension |
| Model-generated progress summary | Authority separation: a narrative is not a record; it cannot be audited or recomputed | `FR-DASH-001`, `INV-PROG-001` |
| Event log placed in the model prompt to "personalise" | Privacy and isolation: raw events and learner text leave the database for a provider call without a need | `INV-SCOPE-001` |
| Project progress from the frontend | Isolation/authority: the client is untrusted; a forged total becomes a displayed record | `INV-PROG-001` |

## Responsibility map

| Element | Responsibility | Implemented in |
|---|---|---|
| `ProgressService` | Append events, project totals, parity check | `src/backend/user_progress/service.py` |
| `ChatRouter` | Emit session/turn events in the same transaction as the turn | `src/backend/api/routers/chat.py` |
| `VocabularyService` | Emit confirmation/review events with dedupe key | `src/backend/vocabulary/service.py` |
| `GrammarEvaluator` | Emit submission events | `src/backend/grammar/evaluator.py` |

## Quality attribute tradeoffs

| Attribute | Tactic | Buys | Costs | Metric that would invalidate |
|---|---|---|---|---|
| Integrity | Append-only events, read-time projection | Totals provably match events | Aggregation query per dashboard read | `progress_mismatch_total > 0` |
| Auditability | Immutable events, correction events | History is defensible | More rows and a correction path | correction without an event |
| Performance | Index on `(user_id, occurred_at)`, projection cache with parity | Fast dashboard at small volume | Parity check adds a query | dashboard p95 > 1 s |
| Cost | No model call for totals | Deterministic and cheap | None material | model-sourced total found |

## Consequences

**Benefits**

- The dashboard is a query, not a state machine; bugs are localised to projection logic.
- Progress totals are provable and replayable from stored events.
- Cross-user tests can assert on events as well as responses.
- The same events feed the evaluation logbook's usage and quality narratives.

**Costs**

- More rows than counters; retention and indexing matter at volume.
- The projection query must be tuned; a naive aggregate can be slow.
- Event schema changes need versioning.

## Review triggers

| Trigger | Threshold | Action |
|---|---|---|
| Parity mismatch | any occurrence | Hide dashboard, recompute, CRITICAL, open a bug diary entry |
| Event volume | > 1M/month | Add monthly partitions; benchmark projections |
| Dashboard p95 | > 1 s | Add a cached projection with parity check |

## Change log

| Date | Change | Evidence |
|---|---|---|
| 2026-10-27 | Initial record model accepted at baseline R1 | `evaluation-logbook.md` 2026-10-27 |
| 2026-11-02 | Rescoped to event-sourced progress; quiz-scoring content removed as not SSOT-backed | This consolidation; `trace-matrix.md` INV-PROG-001 / FR-DASH-001 rows |
