# Runtime policy catalog - baseline R1

**Purpose:** for every failure or degradation path, state what the system does, what it records, when it escalates and which requirement it protects.
**Owner:** Member 3 (Backend & Data); security rows co-owned by Member 5.
**Status:** declared at baseline. No policy has a running test yet; each row names the planned degraded-mode test and is tracked by `DBT-003`.

**Two rules that constrain every row:**

1. **The safety path is never degraded.** Scope control, citation validation and ownership checks run on every path, including failure paths. Only answer quality, availability of AI features or ancillary context may degrade.
2. **No retry is unbounded.** Every retry has an attempt cap, a backoff and an escalation when the cap is reached.

## 1. Policy table

| ID | Trigger (exact condition) | System action | Escalation condition | Related requirement | Degrades / never degrades | Test (planned) |
|---|---|---|---|---|---|---|
| RP-001 | `CitationValidator` rejects output (`citation_unknown`, `abstention_inconsistent`, `tool_request`) | Discard output; no display, no persistence; return a task-specific abstention; append CRITICAL audit | Any `citation_unknown`/`tool_request`; rejection rate > 5% in a rolling week | INV-CITE-001, NFR-QUAL-003 | Answer quality degrades; safety never | `test/offline/test_safety_boundary/test_citation_validator.py::test_reject_invalid_citations` |
| RP-002 | Scope guard rejects input (off-topic, mixed, uncertain) | Return the fixed refusal/clarification string; zero model/retrieval calls; no state mutation | Refusal accuracy < 100% on the fixed off-topic set | INV-SCOPE-002, INV-SCOPE-003, INV-SCOPE-004, INV-SCOPE-005, NFR-QUAL-004 | Nothing degrades; request is refused | `test/offline/test_safety_boundary/test_scope_guard.py::test_fixed_refusal_response` |
| RP-003 | Unparseable JSON, missing field, unknown enum, unknown "action" field | One repair attempt with the schema and error path; if it fails again, RP-001 | Repair success < 50% or reject rate > 5% weekly | INV-CITE-001 | Answer quality degrades; safety never | `test/offline/test_ai_companion/test_tutor.py::test_malformed_output` |
| RP-004 | Model timeout or 5xx after 2 retries; circuit open after 3 failures in 5 min | Stop calling the provider for 5 min; preserve the request; leave completion false; offer retry | 3+ failures in 5 min to on-call; circuit open to release owner | FR-CHAT-001, NFR-PERF-001 | AI turns degrade; deterministic views never | `test/offline/test_ai_companion/test_tutor.py::test_model_timeout` |
| RP-005 | Retrieval returns no chunk above the relevance threshold, or the evidence set is empty | Abstain with an explicit limitation and a generic practice prompt; do not call the model for a grounded answer | No-evidence rate > 20% of grounded questions for 3 days | INV-CITE-001 | Grounded answer withheld; conversation may continue | `test/offline/test_safety_boundary/test_citation_validator.py::test_no_evidence` |
| RP-006 | Retrieval timeout or database error on the retrieval query | Grounded route abstains within 2 s; ordinary conversation may continue only as explicitly ungrounded with zero citations; no fabricated sources | 3+ retrieval failures in 5 min to on-call | INV-SCOPE-006 | Grounding degrades; citation integrity never | `test/offline/test_ai_companion/test_retrieval_conditions.py::test_retrieval_unavailable` |
| RP-007 | A retrieved chunk matches an injection/instruction pattern, or validation sees a policy-escape attempt | Quarantine the chunk; remove from evidence; re-retrieve once; if no safe evidence, abstain; SECURITY event | Any occurrence to security owner | NFR-SEC-001 | Evidence choice degrades; policy never | `test/offline/test_safety_boundary/test_prompt_injection.py::test_zero_policy_escapes` |
| RP-008 | Per-user daily AI call cap reached | Return 429 with reset time; pause only AI endpoints; keep profile, history, vocabulary review and progress available | > 10% of active users hit the cap in a day | NFR-COST-001 | AI features pause; safety and non-AI views never | `test/offline/test_ai_companion/test_token_budget.py::test_daily_cap` |
| RP-009 | Provider 429 or rate-limit response | Bounded exponential backoff (3 attempts, jitter, max 8 s total); then RP-004 safe failure; never bypass the gate to "get an answer" | 5+ rate-limit responses in 10 min to on-call | NFR-PERF-001 | Latency/availability degrades; safety never | `test/offline/test_ai_companion/test_tutor.py::test_rate_limit` |
| RP-010 | Duplicate delivery or client retry of a mutating operation (same `request_id`) | Return the prior committed result; do not append a second turn/event; do not regenerate the model output | A duplicate that changed state (should be impossible) to release owner | INV-PROG-001 | Nothing degrades; duplicate is absorbed | `test/offline/test_user_progress/test_dashboard.py::test_duplicate_delivery` |
| RP-011 | Database unavailable or `/ready` fails | API returns 503 for writes and AI; read-only static pages may load; no model calls; retry with backoff; do not serve stale totals | 1 min continuous unavailability to on-call; 5 min to release owner | INV-PROG-001 | Availability degrades; no partial record | `test/offline/test_user_progress/test_dashboard.py::test_database_unavailable` |
| RP-012 | Request for a record owned by another learner, or identity outside the session | Return 404 with an empty body; no mutation; SECURITY event with resource type only | 5+ denials in 10 min to security owner | INV-AUTH-001 | Nothing; request is denied | `test/offline/test_auth/test_authorization.py::test_cross_user_isolation` |
| RP-013 | 7-day mean session cost or token usage rises > 25% over the prior window | Alert; keep the per-turn token cap; require a REVIEW before the next model-facing change; optionally reduce retrieval count | > 25% drift to release owner; > 50% to project owner | NFR-COST-001 | Cost controls tighten; safety never | `test/offline/test_ai_companion/test_token_budget.py::test_cost_drift_alert` |
| RP-014 | Provider deprecates or removes the pinned model id | Freeze the model id; run the evaluation set against the replacement in a protected environment; require an ADR before switching; no silent model alias | Deprecation date < 30 days to release owner | NFR-QUAL-002, NFR-PERF-001 | Model choice changes only with evidence | `test/live/test_semantic_eval.py::test_model_deprecation_freeze` |
| RP-015 | Profile/registration payload with `language != 'en'` or an invalid CEFR level | Reject with HTTP 422 field errors; no persistence | Any persistence of a non-English or invalid-level profile | INV-LANG-001, INV-CEFR-001 | Nothing; request is rejected | `test/offline/test_auth/test_profile.py::test_reject_non_english` |
| RP-016 | Ingestion manifest points outside `content/`, or a chunk contains an email/learner-text marker, or the runtime attempts a vector write | Reject the ingest; quarantine the source; the runtime write raises permission-denied; SECURITY event | Any occurrence to security owner and content owner | FR-CORP-001, INV-SEC-001, INV-SEC-002 | Corpus is unchanged; runtime write is denied | `test/offline/test_scripts/test_ingestion.py::test_admin_ingest_pipeline` |
| RP-017 | Assembled prompt would exceed the 1,500-token ceiling | Compact history beyond six messages; if still over, reject the over-long current turn with 422 before the model call | Prompt tokens > 1,500 on any turn | NFR-COST-001 | Context length degrades; safety never | `test/offline/test_ai_companion/test_token_budget.py::test_token_cap_enforcement` |
| RP-018 | Render Free instance has spun down; the next request incurs a cold start (~30-50 s) | Serve the request after wake-up; AI turns may exceed the 12 s target on the first request only; emit `cold_start_total`; daily AI cap remains DB-backed and is not reset (`RP-008`) | Cold-start rate > 5% of production requests in a rolling week | NFR-PERF-001, NFR-COST-001; ADR-011 | First-request latency degrades; safety, isolation and stored records never | `test/offline/test_user_progress/test_dashboard.py::test_cap_survives_restart` |

## 2. Retry budgets

| Operation | Attempts | Backoff | Hard stop |
|---|---|---|---|
| Model completion | 2 retries after the first call | jittered, total <= 8 s | RP-004 safe failure; circuit 3 failures/5 min |
| Structured-output repair | 1 | none (same turn) | RP-001 |
| Retrieval query | 1 retry | 100 ms | RP-006 abstention |
| Database write | 1 retry only with the same idempotency key | 50 ms | RP-011 503 |
| Content ingest | 0 automatic retries | n/a | Manual re-run + audit |
| Evaluation replay | 1 retry on infrastructure error | 60 s | RP-014 blocks a model switch |

No row says "retry forever". A retry that cannot succeed within the budget is an escalation, not a loop.

## 3. Coverage decisions

Two paths from the taught catalogue do not exist at runtime in R1 and are recorded here rather than invented:

| Taught path | R1 decision | Justification |
|---|---|---|
| Evaluator unavailable | **Not a runtime path.** Evaluation is an offline release gate; if it cannot run, a model-facing change is blocked rather than degraded per turn. | There is no runtime model judge in R1. |
| Human review queue saturation | **Not applicable.** R1 has no per-turn human review queue; humans review ingestion and PRs, which are batched. | No learner-turn human queue exists. |

## 4. Invariant coverage check

| Invariant | Policies that cover it |
|---|---|
| INV-SCOPE-001 | RP-002 |
| INV-SCOPE-002 | RP-002 |
| INV-SCOPE-003 | RP-002 |
| INV-SCOPE-004 | RP-002 |
| INV-SCOPE-005 | RP-002 |
| INV-SCOPE-006 | RP-006 |
| INV-AUTH-001 | RP-012 |
| INV-LANG-001 | RP-015 |
| INV-CEFR-001 | RP-015 |
| INV-SEC-001 | RP-016 |
| INV-SEC-002 | RP-016 |
| INV-PROG-001 | RP-010, RP-011 |
| INV-CITE-001 | RP-001, RP-003, RP-005 |

ADR-011 adds RP-018 for the Render hosting topology; it covers the cold-start degradation path and the restart-durable AI cap, and does not touch any safety invariant.

All 13 invariants appear in at least one row. No invariant is left with "the happy path handles it".

## 5. Done-when status

- [x] Every row has a planned test in the degraded-mode suite.
- [x] No row says "retry forever"; each retry is bounded and has an escalation.
- [x] Every SSOT `INV-*` appears in at least one row's related-requirement cell (13/13).
- [x] Every row states which parts may degrade and which never do.
- [ ] The degraded-mode suite exists and forces each trigger (`DBT-003`).
- [ ] Escalation recipients are wired to an actual notification channel (`DBT-003`).
