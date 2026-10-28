# Runtime policy catalog - baseline R1

**Purpose:** for every failure or degradation path, state what the system does, what it records, when it escalates and which invariant it protects.
**Owner:** Member 3 (Backend & Data); security rows co-owned by Member 5.
**Status:** declared at baseline. No policy has a running test yet; each row names the planned degraded-mode test and is tracked by `DBT-003`.

**Two rules that constrain every row:**

1. **The safety path is never degraded.** Validation, ownership checks and citation checks run on every path, including failure paths. Only answer quality, availability of AI features or ancillary context may degrade.
2. **No retry is unbounded.** Every retry has an attempt cap, a backoff and an escalation when the cap is reached.

## 1. Policy table

| ID | Trigger (exact condition) | System action | User sees | Evidence captured | Escalation condition | Related INV | Degrades / never degrades | Test (planned) |
|---|---|---|---|---|---|---|---|---|
| RP-001 | `ResponseValidator` rejects output (`schema_invalid`, `citation_unknown`, `tool_request`, `abstention_inconsistent`) | Discard output; no display, no persistence; return task-specific safe fallback or abstention; append CRITICAL audit | "I could not verify that answer. Try rephrasing, or ask for a practice suggestion." | `request_id`, rejection code, task, model_id, prompt_version, corpus_version, validation_id | Any `citation_unknown`/`tool_request`; rejection rate > 5% in a rolling week | INV-001, INV-002, INV-007 | Answer quality degrades; safety never | `test/offline/test_degradation.py::test_validation_reject` |
| RP-002 | Model timeout or 5xx after 2 retries; circuit open after 3 failures in 5 min | Stop calling the provider for 5 min; preserve draft/checkpoint; leave completion false; offer retry | "The tutor is unavailable right now. Your draft is saved; retry in a minute." | `request_id`, failure class, attempts, provider status, circuit state, latency | 3+ failures in 5 min to on-call; circuit open to release owner | INV-006 | AI turns degrade; deterministic views never | `test_degradation.py::test_model_timeout` |
| RP-003 | Unparseable JSON, missing field, unknown enum, unknown "action" field | One repair attempt with the schema and error path; if it fails again, RP-001 | Same as RP-001 after the repair fails | Rejection code, repair count, error path (not raw output) | Repair success < 50% or reject rate > 5% weekly | INV-001 | Answer quality degrades; safety never | `test_degradation.py::test_malformed_output` |
| RP-004 | Output cites `source_id` not in the retrieved set, or a retired/unpublished id | Discard the entire answer; abstain with limitation; log CRITICAL; do not strip and display | "I cannot support that with the current lesson library." | `request_id`, offending id, retrieved id set, corpus_version, prompt_version | Any occurrence to security owner and release owner | INV-002, INV-008 | Nothing degrades; answer is withheld | `test_degradation.py::test_unknown_citation` |
| RP-005 | Retrieval returns no chunk above the relevance threshold, or the evidence set is empty | Abstain with an explicit limitation and a generic practice prompt; do not call the model for a grounded answer | "The lesson library does not cover this yet. Here is a practice suggestion." | `request_id`, query hash, candidate count, top score, threshold, level/topic | No-evidence rate > 20% of grounded questions for 3 days | INV-002 | Grounded answer withheld; conversation may continue | `test_degradation.py::test_no_evidence` |
| RP-006 | Retrieval timeout or database error on the retrieval query | Grounded route abstains within 2 s; ordinary conversation may continue only as explicitly ungrounded with zero citations; no fabricated sources | "Lesson search is unavailable; this reply is not grounded in the library." | `request_id`, failure class, latency, query filters, retry count | 3+ retrieval failures in 5 min to on-call | INV-006 | Grounding degrades; citation integrity never | `test_degradation.py::test_retrieval_unavailable` |
| RP-007 | A retrieved chunk matches an injection/instruction pattern, or the validator sees a policy-escape attempt | Quarantine the chunk; remove from evidence; re-retrieve once; if no safe evidence, abstain; SECURITY event | Normally no visible change; if evidence is gone, the RP-005 message | `chunk_id`, pattern class, source_id, version_id, query hash (not raw text) | Any occurrence to security owner; repeated source to content owner | INV-007 | Evidence choice degrades; policy never | `test_degradation.py::test_injection_in_source` |
| RP-008 | Per-user daily AI call cap reached (`MAX_AI_CALLS_PER_DAY`, default 50) | Return 429 with reset time; pause only AI endpoints; keep profile, history, vocabulary review and progress available | "You have reached today's tutor limit. It resets at 00:00." | `user_ref_hash`, call count, cap, date, endpoint | > 10% of active users hit the cap in a day | INV-006 | AI features pause; safety and non-AI views never | `test_degradation.py::test_daily_cap` |
| RP-009 | Provider 429 or rate-limit response | Bounded exponential backoff (3 attempts, jitter, max 8 s total); then RP-002 safe failure; never bypass the gate to "get an answer" | Retry state, then the unavailable message | `request_id`, attempts, retry-after, provider status | 5+ rate-limit responses in 10 min to on-call | INV-006 | Latency/availability degrades; safety never | `test_degradation.py::test_rate_limit` |
| RP-010 | Checkpoint write fails at turn start | Do not call the model; return a retryable error; no partial turn; no completion | "We could not save this turn. Please retry." | `request_id`, DB error class, checkpoint state, idempotency key | Any occurrence to on-call; 3+ in 10 min to release owner | INV-001, INV-006 | Turn is not attempted; safety never | `test_degradation.py::test_checkpoint_write_failure` |
| RP-011 | Summary write or compaction fails after a committed turn | Commit the turn (summary is context only); enqueue a bounded retry (3 attempts); next turn uses the previous summary; never a partial summary | Normally no visible change | `request_id`, summary_version, retry count, queue depth | Queue depth > 100 or 3 failed attempts to AI owner | INV-011 | Continuity may be stale; decisions never | `test_degradation.py::test_summary_write_failure` |
| RP-012 | Duplicate delivery or client retry of a mutating operation (same `turn_request_id` or `attempt_id`) | Return the prior committed result; do not append a second turn/event/score; do not regenerate the model output | The same result as the first request | `request_id`, idempotency key, original outcome, timestamp | A duplicate that changed state (should be impossible) to release owner | INV-005 | Nothing degrades; duplicate is absorbed | `test_degradation.py::test_duplicate_delivery` |
| RP-013 | Database unavailable or `/ready` fails | API returns 503 for writes and AI; read-only static pages may load; no model calls; retry with backoff; do not serve stale totals | "The service is temporarily unavailable. Retry shortly." | `request_id`, readiness probe, DB error class, duration | 1 min continuous unavailability to on-call; 5 min to release owner | INV-005 | Availability degrades; no partial record | `test_degradation.py::test_database_unavailable` |
| RP-014 | Request for a record owned by another learner, or identity outside the session | Return 404 with an empty body; no mutation; SECURITY event with resource type only | "Not found." (no confirmation the record exists) | `request_id`, actor hash, resource type, action, route | 5+ denials in 10 min to security owner | INV-003 | Nothing; request is denied | `test_degradation.py::test_cross_user_attempt` |
| RP-015 | A retrieved chunk's version is retired or unpublished between retrieval and display | Drop the chunk; re-retrieve once against the active version; if no evidence remains, abstain; do not display the stale citation | Normally no visible change; RP-005 message if evidence is gone | `chunk_id`, version_id, active_version, request_id | Any occurrence to content owner and release owner | INV-008, INV-002 | Answer may abstain; stale citation never | `test_degradation.py::test_retired_mid_flight` |
| RP-016 | 7-day mean session cost rises > 25% over the prior window | Alert; keep the per-session hard cap; require a REVIEW before the next model-facing change; optionally reduce retrieval count | No change unless the hard cap is hit (then RP-008) | Window means, `session_cost_usd`, tokens in/out, model_id, prompt_version | > 25% drift to release owner; > 50% to project owner | INV-006 | Cost controls tighten; safety never | `test_degradation.py::test_cost_drift_alert` |
| RP-017 | Evaluation/canary gate fails on a prompt, corpus, embedding or model change | Block the release and the traffic switch; keep the prior active version; if already deployed, roll back to the prior version; record the eval id | Not user-visible; the old version continues to serve | Eval id, metric values, failing case ids, version ids, CI run | Any invariant failure to release owner immediately | INV-001, INV-002, INV-008 | New version withheld; old version serves | `test_degradation.py::test_eval_gate_blocks` |
| RP-018 | Provider deprecates or removes the pinned model id | Freeze the model id; run EVAL-1.0.0 against the replacement in a protected environment; require an ADR before switching; no silent model alias | Normal service until a planned switch | Old/new model ids, eval results, date, deprecation notice | Deprecation date < 30 days to release owner | INV-001 | Model choice changes only with evidence | `test_degradation.py::test_model_deprecation_freeze` |
| RP-019 | Request contains a client-supplied `score`, a forged `correct_index`, or a score for another attempt | Ignore the field; recompute from the stored key; SECURITY event; return the true score | The true score; no explanation of the forgery | `request_id`, actor hash, attempt id, field name | Any occurrence to security owner; repeated actor to on-call | INV-004 | Nothing; forgery is absorbed | `test_degradation.py::test_forged_score` |
| RP-020 | Ingestion manifest points outside `content/`, or a chunk contains an email/learner-text marker | Reject the ingest; quarantine the source; leave the active version untouched; block publish; SECURITY event | Admin sees "source rejected: privacy boundary" | Manifest hash, source id, rejected reason (not content), request id | Any occurrence to security owner and content owner | INV-009 | Publish is blocked; served corpus unchanged | `test_degradation.py::test_learner_data_ingest` |
| RP-021 | An audit event contains a field outside the allowlist, or a raw-text fingerprint check fails | Drop the field; write only allowlisted fields; send a redacted alert to the security sink; do not retry with the raw value | Not user-visible | Field name, event type, request id, redaction action | Any occurrence to security owner | INV-010 | Logging detail degrades; privacy never | `test_degradation.py::test_redaction_failure` |

## 2. Retry budgets

| Operation | Attempts | Backoff | Hard stop |
|---|---|---|---|
| Model completion | 2 retries after the first call | jittered, total <= 8 s | RP-002 safe failure; circuit 3 failures/5 min |
| Structured-output repair | 1 | none (same turn) | RP-001 |
| Retrieval query | 1 retry | 100 ms | RP-006 abstention |
| Database write | 1 retry only with the same idempotency key | 50 ms | RP-013 503 |
| Summary write | 3 queued attempts | 1 s, 5 s, 30 s | RP-011 alert |
| Content publish | 0 automatic retries | n/a | Manual rollback + audit |
| Evaluation replay | 1 retry on infrastructure error | 60 s | RP-017 blocks release |

No row says "retry forever". A retry that cannot succeed within the budget is an escalation, not a loop.

## 3. Coverage decisions

The taught catalogue expects a row for every degraded path the design admits. Two taught paths do not exist at runtime in R1; they are recorded here rather than invented:

| Taught path | R1 decision | Justification | Would become |
|---|---|---|---|
| Evaluator unavailable | **Not a runtime path.** Evaluation is an offline release gate. If it cannot run, RP-017 fails closed and the release is blocked. | There is no runtime model judge in R1; quality is measured by EVAL-1.0.0 offline/live, not per turn. | A runtime critic (round 2) would need a new RP and an ADR. |
| Human review queue saturation | **Not applicable.** R1 has no per-turn human review queue; humans review corpus publication, evaluation and PRs. | The only human queues are content publication and code review, which are batched, not per learner turn. | If a teacher-review queue is added, a new RP with a priority and SLA is required. |
| Canary gate failure | Covered by RP-017. | There is no traffic-split canary in R1; a prompt/corpus version switch is the deployment unit and is blocked/rolled back by RP-017. | A real canary adds a traffic policy and a new RP. |

## 4. Invariant coverage check

| Invariant | Policies that cover it |
|---|---|
| INV-001 | RP-001, RP-003, RP-010, RP-017 |
| INV-002 | RP-001, RP-004, RP-015, RP-017 |
| INV-003 | RP-014 |
| INV-004 | RP-019 |
| INV-005 | RP-012, RP-013 |
| INV-006 | RP-002, RP-008, RP-009, RP-010, RP-016 |
| INV-007 | RP-001, RP-007 |
| INV-008 | RP-004, RP-015, RP-017 |
| INV-009 | RP-020 |
| INV-010 | RP-021 |
| INV-011 | RP-011 |

All 11 invariants appear in at least one row. No invariant is left with "the happy path handles it".

## 5. Done-when status

- [x] Every row has a planned test in the degraded-mode suite.
- [x] No row says "retry forever"; each retry is bounded and has an escalation.
- [x] Every `INV-*` appears in at least one row's related-invariant cell.
- [x] Every row states which parts may degrade and which never do.
- [ ] The degraded-mode suite exists and forces each trigger (`DBT-003`).
- [ ] Escalation recipients are wired to an actual notification channel (`DBT-003`).
