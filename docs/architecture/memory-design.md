# Memory design - baseline R1

**Purpose:** define what state survives a pause, a crash, a model swap and a version bump; who owns it; how long it lives; and what may never be stored.
**Owners:** Member 3 (Backend & Data) for checkpoints, events and deletion; Member 2 (AI & RAG) for summaries and prompt use.
**Related:** ADR-009, ADR-006, ADR-008, `runtime-policy-catalog.md` RP-010/RP-011/RP-012/RP-013, `invariants.md` INV-009/010/011.

## 1. Two lifetimes, two elements

| Lifetime | Purpose | Store | Owner | Retention | Consumer | Failure behaviour |
|---|---|---|---|---|---|---|
| Short-lived checkpoint | Resume an interrupted turn without duplicating it | `turn_checkpoints` | `PracticeSessionService` | 24 hours | API turn handler | Retry from checkpoint; if expired, start a new turn (`RP-010`) |
| Durable learner memory | Keep continuity across turns and sessions | `session_summaries` | `SessionSummaryStore` | 12 months after last activity | `PromptAssembler` only | Turn may proceed without summary (`RP-011`); never a decision input |
| Durable learning record | Prove what happened and compute totals | `learning_events` | `ProgressLedger` | 24 months | `ProgressLedger.project_progress()` | Transaction rolls back; no partial record (`RP-013`) |

The checkpoint is **per workflow and short-lived**; the summary is **per user and long-lived**. They are separate tables, separate owners and separate failure policies. A checkpoint is never renamed into a summary, and a summary is never used to resume a transaction.

## 2. Checkpoint state

| Field | Type | Why it must survive | Consumer in the resume path |
|---|---|---|---|
| `checkpoint_id` | UUID | Identify the attempt uniquely | Lease acquisition |
| `user_id` | UUID | Scope ownership; never from a request field | `OwnershipGuard` check |
| `session_id` | UUID | Attach the resumed turn to the right session | Session loader |
| `turn_request_id` | string | Idempotency key to prevent a duplicate turn | Unique constraint + lookup |
| `stage` | enum `awaiting_model` `validating` `awaiting_persist` | Know where to resume and which side effects are safe | Resume switch |
| `attempt_count` | smallint | Bound the repair and retry loop | Retry policy (max 2) |
| `draft_text` | text, max 1,500 chars | Preserve the learner's input when the model fails | Re-submit on retry; never written to logs |
| `draft_fingerprint` | char(64) | Correlate without exposing the draft | Audit only |
| `lease_expires_at` | timestamptz | Prevent two workers processing the same turn | Lease acquisition |
| `created_at` / `updated_at` | timestamptz | TTL and orphan cleanup | Cleanup job |

No field is written "just in case". `draft_text` has a consumer (the retry path) and a 24-hour retention. `draft_fingerprint` has a consumer (audit correlation). `attempt_count` has a consumer (bounded retry). A field without a resume consumer is removed.

## 3. Durable store

### `session_summaries`

| Field | Type | Rule |
|---|---|---|
| `summary_id` | UUID | Primary key |
| `user_id` | UUID | One active summary per user; indexed |
| `summary_text` | text | <= 400 tokens; no direct quotes longer than 200 characters |
| `token_count` | integer | Recount on write; reject > 400 |
| `summary_version` | integer | Incremented on each compaction or learner edit |
| `source_turn_range` | int4range | Which turns were compacted; for audit and reproducibility |
| `updated_at` | timestamptz | Retention clock |
| `deleted_at` | timestamptz null | Soft delete, then hard delete after 7 days |

Retrieval interface: `SessionSummaryStore.get(user_id) -> Summary | None`, `upsert(user_id, text, turn_range)`, `delete(user_id)`. Only `PromptAssembler` calls `get`; the learner-facing endpoint calls `upsert`/`delete` through `PracticeSessionService`.

### Durable knowledge beyond the summary

- `learning_events` is the durable record of what happened; it is not "memory" for the model and is never placed in a prompt.
- `content_versions` is durable curriculum knowledge owned by `ContentPublisher`; it is not learner state and is covered by ADR-007.
- Model and prompt versions are recorded per turn in `observability_events`, not stored as learner memory.

## 4. Write and retrieval policy

| Operation | Trigger | Owner | Transaction rule |
|---|---|---|---|
| Create checkpoint | Before the model call, after ownership check | `PracticeSessionService` | Insert with a 60 s lease; unique `(user_id, turn_request_id)` |
| Update stage | After model return, before/after validation | `PracticeSessionService` | Same row; no new checkpoint |
| Delete checkpoint | Successful turn commit or 24 h TTL | `PracticeSessionService` | Same transaction as the turn insert |
| Write summary | After compaction, on learner edit | `SessionSummaryStore` | Separate transaction; failure does not fail the turn |
| Delete summary | Learner request; account deletion | `SessionSummaryStore` | Soft delete, audit event, hard delete after grace |
| Append learning event | Same transaction as the fact | `ProgressLedger` | Append-only; unique idempotency key |
| Append audit event | After validation and on every failure | `ObservabilityStore` | Append-only; redacted fields only |
| Read summary | Prompt assembly only | `PromptAssembler` | Owner-scoped; never in a deterministic service |
| Read events | Dashboard projection | `ProgressLedger` | Owner-scoped; aggregate only |
| Read corpus | Retrieval | `RetrievalService` | Active published chunks only |

### The memory-isolation rule (MUST NOT)

> **MUST NOT:** memory retrieval - a session summary, vocabulary history or any derived learner profile - influence quiz scoring, progress totals, authorization, content eligibility or any invariant decision.

This is deliberately stronger than "should not". It is enforced by an import contract (no decision module may import `SessionSummaryStore`) and by `INV-011`. The test is `test/offline/invariants/test_inv_011_summary_isolation.py`: change a summary, then assert that scores, totals and authorization are unchanged.

## 5. Ownership

| Store | Sole writer | Allowed readers | Forbidden readers |
|---|---|---|---|
| `turn_checkpoints` | `PracticeSessionService` | The same service | Frontend, `TutorPipeline`, `AssessmentService` |
| `session_summaries` | `SessionSummaryStore` | `PromptAssembler`, the learner's own settings endpoint | `AssessmentService`, `ProgressLedger`, `OwnershipGuard`, `ContentPublisher` |
| `messages`, `practice_sessions` | `PracticeSessionService` | Owned session reads, `PromptAssembler` (recent turns) | `RetrievalService` |
| `writing_submissions` | `WritingFeedbackService` | Owner reads; `ContentPublisher` must reject | `ContentPublisher`, `RetrievalService` |
| `learning_events` | `ProgressLedger` | `ProgressLedger.project_progress()` | Model path, `TutorPipeline` |
| `observability_events` | `ObservabilityStore` | Operator metrics only | Any learner-facing endpoint |
| `content_*` | `ContentPublisher` | `RetrievalService` (active only) | Learner services |
| `ai_usage_daily` | `ModelGateway` | Operator cost report | Learner endpoints |

No two elements share a write path. A read that crosses an ownership boundary is a finding, not a convenience.

## 6. Retention

| Store | Retention | Reason | Deletion event |
|---|---|---|---|
| `turn_checkpoints` | 24 hours | Resume window; a draft is not a record | TTL job + successful commit |
| `practice_sessions`, `messages` | 12 months after last activity | Learner history and continuity | Account deletion; purge job |
| `writing_submissions`, `feedback` | 12 months after last activity | Learner's writing evidence | Account deletion; purge job |
| `session_summaries` | 12 months after last activity | Continuity memory | Learner delete; account deletion |
| `learning_events` | 24 months | Progress and audit | Account deletion; aggregate-first purge |
| `quizzes`, `quiz_items`, `attempts` | 12 months | Learning record | Account deletion |
| `vocabulary`, `user_vocabulary` | Until deletion | Learner-owned state | Account deletion |
| `observability_events` (operational) | 30 days | Debugging | Rolling purge |
| `observability_events` (security) | 90 days | Incident review | Rolling purge |
| Daily cost/quality aggregates | 13 months | Trend and report | Rolling purge |
| `ai_usage_daily` | 90 days | Budget enforcement | Rolling purge |
| `content_versions` (active) | Indefinite while published | Curriculum | Retire, not delete |
| `content_versions` (retired) | 24 months | Citation provenance | Purge job after 24 months |
| `users`, `profiles` | Until deletion + 30 days | Identity | Deletion request |

Retention is enforced by scheduled jobs, not by a README promise. A deletion test checks every store for the deleted user within 30 days.

## 7. Privacy

| Data | Never persisted / never exposed |
|---|---|
| Email, display name | Not sent to the model provider; not in `observability_events`; hashed only where correlation is required |
| Learner writing | Not embedded, not indexed, not copied into `content_*`; not in logs; stored only in owner-scoped tables |
| Provider key, session secret | Never in the repository, browser bundle, logs or a prompt; `AppConfig` only |
| Full prompt text | Not logged; only layer sizes and versions |
| Other learners' data | Not in any prompt or response |

- Hashing: `user_ref_hash = SHA-256(user_id + pepper)` computed in `ObservabilityStore`; `text_fingerprint = SHA-256(text)` computed at the logging boundary, never stored with the text.
- Provider disclosure: turn text and retrieved lesson text are sent to the provider for inference. The provider agreement must state no training on submitted data; a change is a review trigger (`R-008`).
- Deletion: a learner deletion request sets a soft-delete flag, schedules a 7-day grace job, then hard-deletes rows in dependency order (messages -> sessions -> writing -> summaries -> vocabulary -> attempts -> events). The audit row retains only the deletion event and the request id.
- Export: not in R1. If added, it must read from the owner-scoped stores only.

## 8. Crash and replay semantics

### Turn transaction

```
acquire lease (SELECT ... FOR UPDATE SKIP LOCKED)
  -> load session + checkpoint
  -> call model (no writes)
  -> validate (no writes)
  -> BEGIN
       insert learner turn
       insert validated tutor turn
       append learning_events
       append observability_event
       delete checkpoint
     COMMIT
  -> release lease
```

| Crash point | Durable state | Recovery |
|---|---|---|
| Before checkpoint create | No checkpoint, no turn | The request can be retried; nothing to clean |
| After checkpoint create, before model call | Checkpoint `awaiting_model` | Lease expires after 60 s; retry resumes at the same stage |
| During model call | Checkpoint `awaiting_model`; provider may have processed the text | Retry with same idempotency key; no turn row exists; provider call is not billed twice by our counter |
| After model, during validation | Checkpoint `validating`; no turn | Retry validation or repair within the attempt cap; discard on expiry |
| After validation, before commit | Checkpoint `awaiting_persist`; no turn | Re-run the commit; the idempotency key prevents a duplicate |
| During commit | Transaction rolls back entirely | Retry; no partial turn, no partial event |
| After commit, before response | Turn committed; checkpoint deleted | Retry returns the committed turn by idempotency key (`RP-012`) |
| During summary write | Turn committed; summary stale | Summary retry queue; the next turn uses the previous summary, never a partial one (`RP-011`) |
| Duplicate delivery | Same `turn_request_id` | Return the prior result; do not append a second event |

- **Atomic write:** one database transaction for the turn, its events and the checkpoint delete. No file-based state for learner data.
- **Lease/TTL:** 60 seconds per checkpoint; a worker crash releases the lease by expiry, not by a human.
- **Idempotency:** `(user_id, turn_request_id)` on checkpoint and turn; `(user_id, attempt_id)` on scoring; `(user_id, event_type, ref)` on events.
- **Replay order:** acquire lease -> replay log -> load checkpoint -> resume stage -> commit -> release. Replaying a committed turn returns the prior result; it never regenerates model output.

## 9. Deletion and correction

| Request | Path | Evidence |
|---|---|---|
| Delete summary | UI -> `PracticeSessionService.delete_summary()` -> `SessionSummaryStore.delete()` | Audit event; next prompt has no summary |
| Correct a quiz score | New regrade event with reason; old attempt stays (`ADR-008`) | Audit trail; dashboard uses the latest event |
| Delete account | Scheduled job across all stores within 30 days | Deletion log with per-store counts; no raw text in the log |
| Retire content | `ContentPublisher.retire()` | Version status; retrieval excludes it (`RP-015`) |

## 10. Done-when checks

- [x] Every checkpoint field has a consumer in the resume path (Section 2 table).
- [x] This design and `runtime-policy-catalog.md` agree on checkpoint, summary and database write failures (RP-010, RP-011, RP-013).
- [x] The document states the memory-isolation rule as a MUST NOT and names the test (`INV-011`).
- [x] The two lifetimes have different tables, owners, retention and failure behaviour.
- [ ] A deletion test proves every store is empty for a deleted user within 30 days (`DBT-003`).
- [ ] `test_inv_011_summary_isolation.py` exists and fails when a summary is read by a decision service (`DBT-003`).
