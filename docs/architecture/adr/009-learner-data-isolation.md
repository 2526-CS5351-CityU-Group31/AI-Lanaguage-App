# ADR-009: Separate short-lived checkpoints from durable learner memory and keep memory out of the decision path

- **Status:** Accepted
- **Date:** 2026-10-27
- **Supersedes:** -
- **Decision owner:** Member 3 (Backend & Data) with Member 2 (AI & RAG)
- **Related requirements:** REQ-LANG-FR-009, REQ-LANG-SEC-004, REQ-LANG-NFR-005, REQ-LANG-INV-001
- **Related artifacts:** `docs/architecture/memory-design.md`, `docs/architecture/invariants.md` INV-009/010/011, `runtime-policy-catalog.md` RP-010/RP-011/RP-013, ADR-006, `permission-model.md`
- **Review triggers:** any deletion request not completed within 30 days; summary `> 400 tokens`; raw learner text found in a log or index sample; checkpoint replay producing a duplicate turn; provider data-policy change; retention change proposal; a summary influencing a score, progress total or authorization decision.

## Context

The platform needs two kinds of memory with different lifetimes and different risks:

- A **short-lived checkpoint** so a turn can resume after a timeout or a crash without duplicating a message.
- A **durable summary** so a learner can return to a session and the tutor retains context across turns.

Conflating them produces the classic failure: a stale checkpoint is mistaken for a durable record, or a durable summary is written into the decision path and changes a score. Learner writing is personal data; the curriculum is licensed content. They must not share a store.

## Decision

Use two stores with separate owners and retention:

1. `turn_checkpoints` - short-lived, per-workflow, 24-hour TTL, deleted on successful commit; owned by `PracticeSessionService`.
2. `session_summaries` - durable, per-user, <= 400 tokens, editable and deletable; owned by `SessionSummaryStore`.

Memory is **context only**. No checkpoint field and no summary value may be read by `AssessmentService`, `ProgressLedger`, `OwnershipGuard`, `RequestAuthenticator` or `ContentPublisher`. The rule is enforced by import contracts (`INV-011`), not by convention.

## Store inventory

| Store | Content | Owner | Write policy | Retention | Privacy |
|---|---|---|---|---|---|
| `turn_checkpoints` | user, session, stage, attempt count, draft ref, lease expires at | `PracticeSessionService` | On turn start; delete on turn commit or 24 h TTL | 24 hours | Owner-scoped; raw draft stays in `writing_submissions` if applicable |
| `session_summaries` | user, bounded summary, version, updated_at | `SessionSummaryStore` | After compaction; on learner edit/delete | 12 months after last activity | No raw quotes beyond 200 chars; editable/deletable |
| `practice_sessions`, `messages` | Session metadata, learner and validated tutor turns | `PracticeSessionService` | On validated turn commit | 12 months after last activity | Personal; not indexed or embedded |
| `writing_submissions`, `feedback` | Original paragraph, validated suggestion, decision | `WritingFeedbackService` | On submit/accept/dismiss | 12 months after last activity | Personal; never enters corpus |
| `learning_events` | Event type, refs, timestamp, actor | `ProgressLedger` | Append-only, same transaction as the fact | 24 months | Pseudonymous refs; no raw text |
| `observability_events` | Request/version/validation/latency/cost fields | `ObservabilityStore` | Append-only per turn and security event | 30 days operational; 90 days security; 13 months cost aggregates | Redacted; `user_ref_hash`, `text_fingerprint` |
| `ai_usage_daily` | user hash, date, calls, tokens, cost | `ModelGateway` | Increment on provider call | 90 days | Pseudonymous; no content |
| `content_versions`, `content_chunks` | Curriculum text, metadata, embeddings | `ContentPublisher` | Versioned transactions | Active indefinitely; retired 24 months | Licensed content only; no learner text |

## Write and retrieval policy

- Checkpoint write: before the model call, `PracticeSessionService` creates a row with a 60-second lease and the idempotency key `(user_id, turn_request_id)`. A commit deletes it in the same transaction that inserts the turn.
- Summary write: only `PromptAssembler` requests a compaction; `SessionSummaryStore` writes the result. The summary is never written by `TutorPipeline` or `ModelGateway`.
- Summary read: `PromptAssembler` may read the owner's summary for context. No deterministic service may import `SessionSummaryStore`.
- Evidence read: `RetrievalService` reads only `content_chunks` joined to active versions. It never reads learner tables.
- Log read: only `ObservabilityStore` exposes metrics; access is operator read-only and never joins to raw learner text.

## Privacy rules

| Data | Rule |
|---|---|
| Email, display name | Stored in `users` only; never logged or sent to the model provider |
| Learner writing | Stored only in owner-scoped `writing_submissions` and `messages`; never embedded, indexed, or copied into the corpus |
| Prompt content | The provider receives the turn text and retrieved lesson text; it does not receive email, display name or other learners' data |
| Logs | `user_ref_hash`, `text_fingerprint`, lengths and versions only; no raw text or full prompt |
| Summary | User-visible, editable and deletable; deletion removes the row and records an audit event |
| Provider training | The team's provider agreement must state no training on submitted data; a change is a review trigger (`R-008`) |
| Account deletion | Cascade within 30 days across sessions, messages, writing, summaries, vocabulary and checkpoints; content rows are unaffected |

## Crash and replay semantics

| Concern | Rule |
|---|---|
| Atomic write | One database transaction per turn: insert learner turn, insert validated tutor turn, append events, delete checkpoint, insert audit row |
| Duplicate delivery | Unique `(user_id, request_id)` on checkpoint and turn; a retry returns the prior committed result |
| Exclusive processing | `SELECT ... FOR UPDATE SKIP LOCKED` plus a 60-second lease on the checkpoint |
| Replay order | acquire lease -> load session and checkpoint -> call model -> validate -> transaction -> release/delete checkpoint |
| Crash mid-write | Transaction rolls back; checkpoint remains until TTL; a retry resumes from the checkpoint, not from a partial turn |
| Provider timeout | `RP-002`: no turn row is committed; draft and checkpoint survive; UI offers retry |
| Summary write failure | The turn may still commit (summary is context only); a retry queue records the pending summary (`RP-011`) |
| Deletion | Soft-delete flag with a 7-day grace, then hard delete; audit retains only the deletion event |

## Rationale

- Different lifetimes are different architectural elements. A 24-hour checkpoint and a 12-month summary have different failure modes, retention rules and privacy exposure.
- Keeping memory out of the decision path makes `INV-011` a static import rule, not a reviewer's promise. This is the lecture's point made concrete: an invariant becomes architecture when a dependency is impossible.
- A bounded summary is inspectable by the learner and cheap enough to inject; a full transcript is neither.
- A checkpoint with a lease and an idempotency key is the minimum needed to survive a crash without duplicate turns.
- Separating curriculum and learner stores keeps the corpus licensable and the vector index free of personal data.

## Alternatives considered

| Option | Failed criterion | Evidence |
|---|---|---|
| One long-lived store for checkpoints and summaries | Privacy and ownership: a stale checkpoint becomes a durable record and deletion becomes ambiguous | `SEC-004`, `INV-010` |
| Full transcript in every prompt | Cost and latency: unbounded context; also retains raw text in provider requests longer than needed | `COST-002`, ADR-006 |
| Memory retrieval used to personalise scores or progress | Authority: memory would influence deterministic records; the decision path becomes non-reproducible | `INV-011`, `INV-005` |
| External memory service | Testability and privacy: another processor and a network contract for state the database can hold | `evaluation-table.md` C3 |
| No durable summary | Continuity: every return to a session loses context | `FR-009` |

## Consequences

**Benefits**

- Checkpoint crashes and provider timeouts do not duplicate turns or lose the learner's draft.
- The summary is bounded, inspectable and deletable, which is defensible in the report.
- `INV-011` is enforceable by import-linter; memory cannot silently become a score input.
- Personal data and licensed content have clear store boundaries.

**Costs**

- Two more tables and a retry queue for summary writes.
- Compaction adds a model call and a latency spike at the trigger.
- Deletion is a multi-table operation that needs a test and an audit trail.
- The 24-hour checkpoint TTL means a learner who leaves mid-turn for a day returns to a new turn.

## Review triggers

| Trigger | Threshold | Action |
|---|---|---|
| Deletion SLA | any request beyond 30 days | Incident, security event, process fix |
| Raw text in logs/index | any sample match | Purge, add redaction test, block release |
| Summary length | > 400 tokens | Reject summary write; tighten prompt |
| Memory-decision coupling | any import or read | INV-011 failure; remove the dependency |
| Provider policy change | any change | Reassess disclosure; new ADR if retention changes |
| Duplicate turn | any occurrence | Inspect lease/idempotency; add regression test |

## Change log

| Date | Change | Evidence |
|---|---|---|
| 2026-10-27 | Initial memory and privacy model accepted at baseline R1 | `memory-design.md`; `evaluation-logbook.md` 2026-10-27 |
