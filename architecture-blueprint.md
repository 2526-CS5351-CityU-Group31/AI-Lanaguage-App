# Architecture Blueprint - LANG baseline R1

**Project:** AI Language Learning Platform (English for Chinese-speaking learners)
**Baseline:** R1, frozen 2026-10-27
**Owner:** Member 3 (Backend & Data), with Member 2 (AI & RAG) for the retrieval and tutor boundary
**Status:** Accepted - this file is an executable constraint, not an introduction.
**Companions:** `docs/req/requirements.yaml` (what must hold), `docs/architecture/adr/` (why), `docs/architecture/invariants.md` (what must never happen), `docs/code-governance/` (how it is enforced).

> **Agent reading order (verbatim, also in `AGENTS.md`):** requirements -> blueprint -> ADR -> invariants -> trace matrix -> memory design -> permission model -> runtime policy catalog -> `structural-constraints.md` -> `verification-constraints.md` -> `mcp-tool-manifest.md`. The manifest is last because it is derived from the ADR; reading it first invites the agent to treat tools as the design.

**The single sentence this system exists to guarantee:** a learner-visible answer and every learning record are produced by deterministic code that has accepted validated evidence; model text never becomes authority.

---

## 1. Scope

### 1.1 In scope for R1

| Capability | Boundary of the R1 commitment |
|---|---|
| Account and profile | Register, log in/out, read and update own profile; target language fixed to English, level A1-B1 |
| Practice conversation | Topic and level selection, text turns, follow-up question, bounded history |
| Writing feedback | Original preserved, suggestion separate and labelled, accept/dismiss |
| Grounded lesson help | Published-corpus retrieval, citation by lesson title and section, explicit abstention |
| Vocabulary | Candidate confirmation, definition and example, per-user review state, dedupe by word+sense |
| Quiz | Server-held key, deterministic scoring, explanation, next-practice suggestion |
| Progress | Totals projected from `learning_events`, not model narrative |
| Content administration | Ingest dry run, preview, transactional publish, retire |
| Operations | Offline deterministic suite, controlled live evaluation, redacted observability, cost caps |

### 1.2 Explicitly out of scope

Speech and pronunciation, additional languages, teacher portal, payments, open web browsing, social features, mobile native apps, fine-tuning on learner data, and any model tool that can read or write learner records. A change to this list requires an ADR and a new requirement baseline (see `REQ-LANG-ARCH-004`).

### 1.3 Non-negotiable guarantees

1. No unvalidated model output reaches a learner or a stored record (`INV-001`).
2. No citation outside the retrieved published set is displayed (`INV-002`).
3. No learner reads or writes another learner's record (`INV-003`).
4. Scores and progress are computed by code from stored events (`INV-004`, `INV-005`).
5. Safety validation is never skipped on a failure path (`INV-006`).
6. Retrieved text cannot change policy or authority (`INV-007`).
7. Only published content serves (`INV-008`).
8. Learner writing never enters the shared corpus, index, or logs (`INV-009`, `INV-010`).

---

## 2. Drivers

Requirement clusters are defined once in `docs/req/requirements.yaml`; this table imports them and adds the architectural tradeoff.

| Cluster | Priority | Requirements | Tradeoff taken | Non-negotiable? |
|---|---|---|---|---|
| CL-AUTHORITY | must | 6 | One validation gate adds latency to every AI feature and fails closed | Yes |
| CL-ISOLATION | must | 6 | No shared sessions or demo-account shortcuts; every read is owner-scoped | Yes |
| CL-GROUNDING | must | 7 | Answers limited to a small reviewed corpus; abstention over fluency | Yes |
| CL-RECORD | must | 7 | Read-time aggregation instead of denormalised counters; confirmation steps in UX | Yes |
| CL-RESILIENCE | must | 4 | Fail closed on retrieval/model failure; retry states instead of partial answers | Yes |
| CL-COST | must | 2 | Context and output budgets cap answer richness; heavy users pause | Yes |
| CL-EVOLUTION | must | 4 | Versioned publication and replay cost review time on every model-facing change | Yes |
| CL-ACCESS | should | 1 | Custom controls take longer; accessibility is a release gate for five flows | No |
| CL-GOVERNANCE | must | 3 | Human plan approval before every build round; agent cannot self-approve | Yes |

**Conflict resolved in ADR-001:** grounding quality (CL-GROUNDING) pulls toward a larger corpus and more retrieved context, while cost (CL-COST) and latency (CL-RESILIENCE) pull toward less. The resolution is top-5 retrieval under a fixed token budget, with abstention when the relevance threshold is not met - never a larger prompt.

**Conflict resolved in ADR-005:** helpfulness (CL-GROUNDING) pulls toward free-form prose, while authority (CL-AUTHORITY) pulls toward structure. The resolution is a constrained JSON contract plus one bounded repair attempt; a second failure becomes a safe fallback.

---

## 3. Boundaries

### 3.1 System boundary

```
Browser (text UI, no secrets)
   | HTTPS, session cookie
   v
ApiGateway --> RequestAuthenticator --> OwnershipGuard
   |                                        |
   +--> LearnerProfileService               |
   +--> PracticeSessionService <------------+
   +--> WritingFeedbackService <------------+
   +--> VocabularyService <-----------------+
   +--> AssessmentService <-----------------+--> ProgressLedger --> PostgreSQL
   +--> TutorPipeline
          |  (advisory zone)
          +--> RetrievalService --> PostgreSQL/pgvector (published chunks only)
          +--> PromptAssembler
          +--> ModelGateway --> hosted LLM / embedding API
          +--> ResponseValidator (authoritative veto)
          +--> DegradationController (authoritative failure action)
   |
   +--> ContentPublisher (reviewer-only) --> content sources/versions/chunks
   +--> ObservabilityStore --> observability_events (redacted)
```

### 3.2 Trust boundaries

| Boundary | Inside | Outside | Rule |
|---|---|---|---|
| Browser / API | Server session, authorization, scoring, secrets | Untrusted user input, client state | The browser never chooses a user_id, never holds a provider key, never computes a score |
| API / model provider | Deterministic validation, policy, persistence | Model output treated as an untrusted proposal | No model output is displayed or persisted before `ResponseValidator` |
| API / curriculum corpus | Published, licensed, reviewed content | Learner writing and unpublished drafts | Retrieval filters `published` before ranking; learner text never enters the corpus |
| API / database | Owner-scoped repositories, migrations | Direct table access from model code | Only domain services call repositories; `TutorPipeline` has no write path |
| Operator / learner data | Redacted metrics, audits | Raw learner writing | Logs store references and fingerprints, never raw paragraphs |

### 3.3 Advisory and authoritative zones

- **Advisory zone:** `ModelGateway`, `PromptAssembler`, `TutorPipeline`. These may propose text, citations, quiz drafts and suggestions. They may not write state.
- **Authoritative zone:** `ResponseValidator`, `OwnershipGuard`, `AssessmentService`, `ProgressLedger`, `ContentPublisher`, `DegradationController`, `AppConfig`. These decide what is shown, stored, scored, served or done on failure.
- The boundary is crossed in one direction only: advisory proposal -> validator verdict -> deterministic service action.

---

## 4. Components

One architectural element per module; module and class names are frozen by `docs/code-governance/structural-constraints.md` S1.

| Element | Responsibility | Interface | Module |
|---|---|---|---|
| `ApiGateway` | HTTP boundary, request typing, rate and size limits, error mapping | `handle(request) -> Response` | `src/api_gateway.py` |
| `RequestAuthenticator` | Verify session, produce `Principal`, log denials | `authenticate(cookie) -> Principal \| Denial` | `src/request_authenticator.py` |
| `OwnershipGuard` | Authorize every record access against the principal | `authorize(principal, resource_ref, action) -> Allowed \| Denied` | `src/ownership_guard.py` |
| `LearnerProfileService` | Validate and persist profile fields, language and level | `get_profile()`, `update_profile(patch)` | `src/learner_profile_service.py` |
| `PracticeSessionService` | Create sessions, append ordered turns, read owned history | `create_session()`, `append_turn()`, `get_session()` | `src/practice_session_service.py` |
| `WritingFeedbackService` | Preserve original, request feedback, accept/dismiss suggestion | `submit_writing()`, `decide_suggestion()` | `src/writing_feedback_service.py` |
| `VocabularyService` | Confirm candidates, dedupe by word+sense, update review state | `list_words()`, `confirm_candidate()` | `src/vocabulary_service.py` |
| `AssessmentService` | Validate quiz items, store keys, score attempts deterministically | `create_quiz()`, `submit_attempt()` | `src/assessment_service.py` |
| `ProgressLedger` | Append learning events, project dashboard totals | `append_event()`, `project_progress()` | `src/progress_ledger.py` |
| `ContentPublisher` | Enforce provenance, validate versions, activate/retire atomically | `ingest()`, `publish()`, `retire()` | `src/content_publisher.py` |
| `RetrievalService` | Filter published/language/level/topic, rank and dedupe evidence | `search(query, filters) -> EvidenceSet` | `src/retrieval_service.py` |
| `PromptAssembler` | Build layered context within the token budget, compact history | `assemble(context) -> Prompt` | `src/prompt_assembler.py` |
| `ModelGateway` | Provider adapter, timeout, bounded retry, cost and call budget | `complete(prompt, schema)`, `embed(texts)` | `src/model_gateway.py` |
| `ResponseValidator` | Validate schema, citations, lengths and abstention consistency | `validate(output, evidence) -> Verdict` | `src/response_validator.py` |
| `DegradationController` | Map a failure trigger to the runtime policy action | `decide(failure) -> DegradationAction` | `src/degradation_controller.py` |
| `TutorPipeline` | Orchestrate retrieve -> assemble -> call -> validate; return a proposal | `handle_turn(task) -> TutorProposal` | `src/tutor_pipeline.py` |
| `SessionSummaryStore` | Persist a bounded, user-scoped summary for continuity | `get()`, `upsert()`, `delete()` | `src/session_summary_store.py` |
| `ObservabilityStore` | Append redacted turn/security events, expose metrics | `append_turn_event()`, `append_security_event()` | `src/observability_store.py` |
| `AppConfig` | Load, validate and freeze configuration; only reader of `os.environ` | `load() -> AppConfig` | `src/config.py` |

Support packages that are not architectural elements: `src/contracts/` (typed DTOs, ports, enums), `src/db/` (connection, unit of work, repository primitives). They contain no domain decision and are subject to S1-S7 in `structural-constraints.md`.

---

## 5. Authority

| Element | Authority | May override | May never override | Failure if removed |
|---|---|---|---|---|
| `ResponseValidator` | Authoritative veto over model output | Nothing; it is the final gate | Any deterministic service | Unvalidated text reaches learners |
| `OwnershipGuard` | Authoritative allow/deny for record access | Nothing on the request path | Any service or admin route without audit | Cross-user exposure |
| `RequestAuthenticator` | Authoritative identity | Nothing | Any payload or query field | Identity spoofing |
| `AssessmentService` | Authoritative score and quiz key | Learner-visible explanation text | `ProgressLedger` event semantics | Forged or inconsistent scores |
| `ProgressLedger` | Authoritative event log and projections | Cached projections | Any model narrative | Dashboard drift |
| `ContentPublisher` | Authoritative publish state and version | Retrieval filters | Retrieval ranking | Unpublished content served |
| `DegradationController` | Authoritative failure action | Retry routing | `ResponseValidator` or `OwnershipGuard` | Unsafe fallback text |
| `AppConfig` | Authoritative validated configuration | Default values | Secret validation rules | Startup with invalid configuration |
| `ApiGateway` | Boundary only; no domain decision | Transport concerns | Authorization or validation | No typed entry point |
| `LearnerProfileService` | Authoritative profile fields | Frontend display state | Identity or level checks in other services | Invalid profile/level |
| `PracticeSessionService` | Authoritative session owner and turn order | Nothing | `OwnershipGuard` | Reassigned or reordered sessions |
| `WritingFeedbackService` | Authoritative accept/dismiss state | UI presentation | Original text immutability | Silent overwrite |
| `VocabularyService` | Authoritative confirmation and review state | UI suggestions | `OwnershipGuard` | Unconfirmed mastery |
| `RetrievalService` | Authoritative eligibility filter; advisory relevance | Candidate ranking | Published-only filter | Unpublished/off-level evidence |
| `PromptAssembler` | Advisory assembly | Layer order within ADR-006 | System policy or schema | Budget overflow |
| `ModelGateway` | Advisory external call and budget enforcement | Retry choice within policy | Safety gate | Unbounded spend |
| `TutorPipeline` | Advisory orchestration | Turn routing | Any authoritative element | No proposal, no write |
| `SessionSummaryStore` | Read-only input to context | Summary content | Scores, progress, authorization | Continuity only |
| `ObservabilityStore` | Record-only | Nothing | Any decision | No audit trail |

**Override rules**

- A model may never override `ResponseValidator`, `OwnershipGuard`, `AssessmentService`, `ProgressLedger` or `ContentPublisher`.
- A frontend may never override a score, progress total, identity or citation.
- A human operator may pause AI features or roll back a version; a human may not bypass the validator in a production path.
- Only an accepted ADR plus a human approval may change an authority boundary.

---

## 6. Workflow

| Stage | May do | May not do | Human gate |
|---|---|---|---|
| Plan | Read requirements/ADR/invariants; produce a plan with requirement IDs, files, interfaces, negative tests and rollback | Write `src/`, `frontend/`, `prompts/` or CI | Human approves the plan before any code (`REQ-LANG-GOV-005`) |
| Build | Write permitted source, tests and docs; run Tier 1/2 locally | Touch protected paths, approve its own plan, change thresholds | Reviewer confirms approval artifact and AI log entry |
| Verify | Run Tiers 1-3, add tests and evidence, update trace status | Modify `src/` or relax a threshold | Verification evidence linked in the PR |
| Review | Write a review memo with P0/P1/P2 findings and a verdict | Approve its own PR or waive a P0 without an invariant/ADR citation | Named human reviewer signs the memo |
| Release | Publish corpus/prompt versions and deploy the accepted build | Skip Tier 3 or release with an invariant failure | Human release owner approves with a rollback step |

The stage sequence is Plan -> Build -> Verify -> Review -> Release. No stage may run the next stage's actions; an agent that finishes Build does not self-verify a release gate.

---

## 7. Permissions

**Default rule: no read, no write, unless explicitly whitelisted.** The full path table and hook mapping is owned by `docs/architecture/permission-model.md`; this is a summary only.

| Path group | Plan agent | Build agent | Verify agent | Human required? |
|---|---|---|---|---|
| `docs/req/**` | read | read | read | yes - baseline change |
| `docs/architecture/adr/**`, `architecture-blueprint.md` | read | read | read | yes - ADR/blueprint change |
| `docs/architecture/**` registers | read | read/write for status/evidence only | read/write evidence | yes for rule changes |
| `src/response_validator.py`, `src/ownership_guard.py`, `src/degradation_controller.py` | read | **no access** | read | yes - human + ADR |
| `src/**` (other modules), `frontend/**`, `scripts/**` | read | write (guarded) | read | plan approval + review |
| `migrations/**` | read | write before first apply; frozen after | read | reviewer + rollback plan |
| `prompts/**`, `content/**`, `.github/workflows/**`, `.opencode/**`, `.agent/**` | read | **no access** | read | yes |
| `test/**` | read | write after test approval | read/write evidence | approval artifact |
| `docs/ai-use-log.yaml` | read | append via tool only | read | session owner verifies |
| `transcripts/**`, `.env` | no access | no access | no access | humans only |

---

## 8. Verification

The canonical gate commands (byte-identical to `docs/code-governance/verification-constraints.md`):

```bash
python scripts/validate_req.py docs/req/requirements.yaml
python scripts/check_trace.py
python scripts/check_permissions.py
python scripts/check_manifest.py
pytest test/structural -q
mypy --strict src
pytest test/offline -q
python scripts/run_eval.py --suite evals/EVAL-1.0.0.yaml --offline
python scripts/run_eval.py --suite evals/EVAL-1.0.0.yaml --live
npm --prefix frontend run test:a11y
python scripts/check_ai_log.py --pr $PR
```

| Tier | Commands | Blocks | Failure action |
|---|---|---|---|
| 1 - structural | validate_req, check_trace, check_permissions, check_manifest, `pytest test/structural` | Any merge | Stop; fix structure; no Tier 2 run |
| 2 - correctness | `mypy --strict src`, `pytest test/offline` | Any merge | Stop; fix or revert |
| 3 - behavioral | offline replay, live replay, accessibility | Release and model-facing merge | Human review; invariant failure blocks; quality miss requires a decision record |

**Release thresholds:** citation validity 100%, retrieval recall@5 >= 0.85, grounded correctness >= 0.80 human-scored, policy escape 0, cross-user exposure 0, p95 turn latency <= 12 s, p95 retrieval <= 800 ms, session cost <= US$0.04, axe critical violations 0. Thresholds are owned by `requirements.yaml`; this table must not drift from it.

Tier 1 must pass before Tier 2 starts; Tier 2 before Tier 3. No parallelism across tiers. Live evaluation requires controlled credentials and human approval, and fails closed for a release-bound change.

---

## 9. Observability

| Field | Example | Purpose | Contains personal data? |
|---|---|---|---|
| `request_id` | `req_01J...` | Join API, turn and audit records | no |
| `user_ref_hash` | `sha256:...` | Per-user cost and abuse detection without identity | pseudonymous |
| `task_type` | `conversation`, `lesson_help`, `writing`, `quiz` | Segment quality and cost | no |
| `model_id` | provider model identifier | Attribute behaviour to a model | no |
| `prompt_version` | `prompt_v1.0.0` | Attribute behaviour to a prompt | no |
| `corpus_version` | `corpus-C1.0.0` | Attribute behaviour to content | no |
| `index_version` | `idx-C1.0.0` | Attribute retrieval changes | no |
| `retrieved_chunk_ids` | `["c-0012", "c-0031"]` | Reproduce retrieval and citation validity | no |
| `retrieval_scores` | `[0.82, 0.77]` | Diagnose thresholds | no |
| `validation_result` | `accepted`, `rejected_citation`, `rejected_schema` | Measure the gate | no |
| `degradation_policy_id` | `RP-002` | Confirm the failure path taken | no |
| `latency_ms` | `3120` | SLO tracking | no |
| `tokens_in` / `tokens_out` | `2410` / `380` | Cost accounting | no |
| `cost_estimate_usd` | `0.0041` | Budget tracking | no |
| `outcome` | `answered`, `abstained`, `safe_fallback` | Product and safety metrics | no |
| `text_fingerprint` | `sha256:...` | Correlate a turn without storing text | pseudonymous |

- **Storage:** `observability_events` in PostgreSQL, append-only, operator read-only role.
- **Retention:** 30 days operational detail; 90 days security events; 13 months daily cost and quality aggregates.
- **Prohibited:** raw learner writing, email, display name, provider keys, full prompt text. A redaction test samples 100 events (`INV-010`).
- **Metrics:** `validation_reject_total`, `citation_reject_total`, `cross_user_denial_total`, `injection_escape_total`, `ai_turn_latency_seconds`, `llm_failure_total`, `no_evidence_total`, `ai_calls_per_user_day`, `session_cost_usd`, `progress_mismatch_total`, `scoring_mismatch_total`.
- **Per-requirement counters:** the trace matrix names additional counters (`citation_bypass_total`, `safety_bypass_total`, `unpublished_chunk_served`, `progress_total_mismatch_total`); all are emitted by `ObservabilityStore` with the `<domain>_<event>_total` convention.
- **Alerts:** invariant violation -> CRITICAL; cost 7-day drift > 25% -> REVIEW; p95 > 12 s for 3 days -> REVIEW; cross-user denial burst > 5 in 10 minutes -> security alert.

---

## 10. Change policy

| Change | ADR required? | Human approval? | Additional artifact |
|---|---|---|---|
| Bug fix that preserves all contracts and thresholds | No | Reviewer | Regression test + AI log entry |
| Test, docs typo, comment, non-frozen copy edit | No | Reviewer | - |
| New dependency or package | Yes | Yes | Structural constraints module/import update |
| New component, module or authority change | Yes | Yes | Blueprint Section 4, ADR responsibility map, manifest |
| Validation rule, response schema or score rule change | Yes | Yes | Invariants, trace matrix, tests, eval replay |
| Threshold or metric change | No, if tightening; yes, if relaxing | Yes | Requirements delta, evaluation logbook row |
| Prompt, corpus, embedding or model change | Yes for scope; version bump required | Yes - content/prompt owner | EVAL-1.0.0 replay evidence |
| Retention, privacy or permission change | Yes | Yes | Memory design, permission model, compliance note |
| Deploy topology or hosting change | Yes | Yes | Runtime policy catalog, rollback plan |
| Emergency rollback | Retrospective within 5 working days | On-call + release owner | Incident row in evaluation logbook, bug diary entry |

- Accepted ADRs are immutable; a new ADR supersedes the old one and both remain in the repository.
- Requirements changes create a new baseline (`R2`) with a delta block; IDs are never reused or renumbered.
- A change may not delete a frozen row to hide history; it appends, marks superseded/retired, and links the replacement.

---

## 11. Filesystem

```
README.md
AGENTS.md
Prompt.md
Report.md
architecture-blueprint.md
docs/
  README.md
  req/{prd.yaml, requirements.yaml, req-schema.json}
  architecture/
    adr/{001-guarded-monolith.md, 005-validated-response-contract.md, 006-layered-context.md,
         007-transactional-publishing.md, 008-event-sourced-records.md, 009-memory-and-privacy.md,
         010-agent-tool-boundary.md}
    invariants.md
    trace-matrix.md
    memory-design.md
    option-ledger.md
    permission-model.md
    evaluation-logbook.md
    risk-list.md
    evaluation-table.md
    runtime-policy-catalog.md
    configuration-governance.md
  code-governance/{structural-constraints.md, verification-constraints.md, mcp-tool-manifest.md}
  ai-use-log.yaml
  review-memo.md
  debt-register.md
  bug-diary.md
src/                    # 19 element modules + contracts/ + db/
frontend/               # React + TypeScript learner UI
test/offline/           # deterministic, no network, stub model/retrieval
test/live/              # controlled provider evaluation, credentials required
test/structural/        # import and architecture fitness functions
scripts/                # validation, trace, permissions, cost, eval runners
migrations/             # ordered SQL migrations
content/                # licensed sources, manifest.yaml, vocabulary CSV
evals/                  # EVAL-1.0.0.yaml and fixtures
prompts/                # versioned prompt files, prompt_v1.0.0.yaml
transcripts/            # raw annotated agent sessions (humans only)
.github/workflows/ci.yml
docker-compose.yml
.env.example
```

| Frozen path | Frozen in round | Rule |
|---|---|---|
| `docs/req/requirements.yaml` | R1 | Changes only as a new baseline delta (R2) |
| `docs/architecture/adr/001-*.md`, `005-*.md` ... `010-*.md` | R1 | Append-only; never edit an accepted ADR; supersede with a new ID |
| `architecture-blueprint.md` | R1 | Change requires an ADR and human approval |
| `prompts/prompt_v1.0.0.yaml` | R1 | Immutable once used in evaluation; a change is a new version |
| `evals/EVAL-1.0.0.yaml` | R1 | Frozen evaluation set; a change creates EVAL-1.1.0 and a logbook row |
| Applied `migrations/*.sql` | R1 | Immutable after first apply; corrections are new migrations |
| Published `content/` versions | R1 | Immutable; retirement is a state change, not deletion |
| `.opencode/rules.md`, `.agent/rules.md`, `.opencode/permissions.jsonc` | R1 | Human-only writes; agent read-only |
| `.github/workflows/ci.yml` | R1 | Human-only writes; branch protection depends on it |
| `transcripts/**` | R1 | Append-only raw record; never edited to look better |

**Rules that override convenience:**

- `MUST NOT` modify a frozen directory; frozen paths are listed with the build round they were frozen in.
- `MUST NOT` add a dependency that is not in the module table's `imports from` column.
- `MUST` call the deterministic gate after every model output, before any state mutation.
- `MUST` stop for human approval before generating code in a new build round.

---

## Appendix A - Trace to architecture artifacts

| Concern | Owning artifact | Enforcing artifact |
|---|---|---|
| Requirement registry | `docs/req/requirements.yaml` | `scripts/validate_req.py` (planned), CI gate |
| Architecture choice and rejected options | ADR-001, `evaluation-table.md`, `option-ledger.md` | Review |
| Validation gate and response contract | ADR-005, `invariants.md` INV-001/002 | `ResponseValidator` tests |
| Context layers and token budget | ADR-006 | `PromptAssembler` tests |
| Publication and retrieval eligibility | ADR-007, `runtime-policy-catalog.md` RP-015 | `ContentPublisher`/`RetrievalService` tests |
| Scores and progress | ADR-008 | `AssessmentService`/`ProgressLedger` tests |
| State, retention and privacy | ADR-009, `memory-design.md` | INV-009/010/011 tests |
| Agent tool boundary and approvals | ADR-010, `mcp-tool-manifest.md`, `permission-model.md` | hooks and CI gates |
| Configuration | `configuration-governance.md` | `AppConfig` startup tests and S5 |
