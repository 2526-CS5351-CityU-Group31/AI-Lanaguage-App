# Architecture Blueprint - LANG baseline R1

**Project:** AI Language Learning Platform (English for Chinese-speaking learners)
**Baseline:** R1, frozen 2026-10-27
**Owner:** Member 3 (Backend & Data), with Member 2 (AI & RAG) for the retrieval and tutor boundary
**Status:** Accepted - this file is an executable constraint, not an introduction.
**Companions:** `docs/req/requirements.yaml` (what must hold, the single source of truth), `docs/architecture/adr/` (why), `docs/architecture/invariants.md` (what must never happen), `docs/code-governance/` (how it is enforced).

> **Agent reading order (verbatim, also in `AGENTS.md`):** requirements -> blueprint -> ADR -> invariants -> trace matrix -> memory design -> permission model -> runtime policy catalog -> `structural-constraints.md` -> `verification-constraints.md` -> `mcp-tool-manifest.md`. The manifest is last because it is derived from the ADR; reading it first invites the agent to treat tools as the design.

**The single sentence this system exists to guarantee:** a learner-visible answer and every learning record are produced by deterministic code that has accepted validated evidence; model text never becomes authority.

---

## 1. Scope

### 1.1 In scope for R1

| Capability | Boundary of the R1 commitment |
|---|---|
| Account and profile | Register, log in/out, read and update own profile; target language fixed to English, level A1-B2 |
| Practice conversation | Topic and level selection, text turns, follow-up question, bounded history |
| Writing feedback | Original preserved, suggestion separate and labelled, accept/dismiss |
| Grounded lesson help | Published-corpus retrieval, citation by lesson title and section, explicit abstention |
| Vocabulary | Candidate confirmation, definition and example, per-user familiarity state, dedupe by word+sense |
| Progress | Totals projected from `learning_events`, not model narrative |
| Content administration | Offline ingest (dry run, validate, index) of reviewed lesson documents |
| Operations | Offline deterministic suite, controlled live evaluation, cost/token caps |

### 1.2 Explicitly out of scope

Speech and pronunciation, additional languages, teacher portal, payments, open web browsing, social features, mobile native apps, fine-tuning on learner data, and any model tool that can read or write learner records. A change to this list requires an ADR and a new requirement baseline.

### 1.3 Non-negotiable guarantees

These are the 13 invariants owned by `docs/req/requirements.yaml`; this list is a summary, the registry is authoritative.

1. Every user message passes scope control before retrieval or model invocation (`INV-SCOPE-001`).
2. Off-topic requests receive the fixed refusal with zero model tokens (`INV-SCOPE-002`).
3. A rejected request makes zero retrieval/model calls (`INV-SCOPE-003`).
4. Uncertain and mixed intents return a fixed clarification and never bypass scope control (`INV-SCOPE-004`, `INV-SCOPE-005`).
5. Retrieval runs only when `requires_grounding` is true (`INV-SCOPE-006`).
6. No learner reads or writes another learner's record (`INV-AUTH-001`).
7. Only the English language is accepted; only CEFR A1/A2/B1/B2 (`INV-LANG-001`, `INV-CEFR-001`).
8. The runtime vector store is read-only and there are zero upload endpoints (`INV-SEC-001`, `INV-SEC-002`).
9. Dashboard totals are aggregated from stored events, never from model output (`INV-PROG-001`).
10. Every displayed citation resolves to a retrieved published chunk, else the answer abstains (`INV-CITE-001`).

---

## 2. Drivers

Requirement clusters are defined once in `docs/req/requirements.yaml`; this table imports them and adds the architectural tradeoff.

| Cluster | Priority | Tradeoff taken | Non-negotiable? |
|---|---|---|---|
| CL-SCOPE | must | Bounded deterministic intent classification adds latency to every request | Yes |
| CL-AUTHORITY | must | One validation gate adds latency to every AI feature and fails closed | Yes |
| CL-ISOLATION | must | No shared sessions or demo-account shortcuts; every read is owner-scoped | Yes |
| CL-GROUNDING | must | Answers limited to a small reviewed corpus; abstention over fluency | Yes |
| CL-RECORD | must | Read-time aggregation instead of denormalised counters; confirmation steps in UX | Yes |
| CL-RESILIENCE | must | Fail closed on retrieval/model failure; retry states instead of partial answers | Yes |
| CL-COST | must | A 1,500-token prompt budget and compaction cap answer richness | Yes |
| CL-LOCALE | must | English only, A1-B2 only, to bound content and evaluation complexity | Yes |
| CL-SECURITY | must | Read-only corpus, zero uploads, owner-scoped data | Yes |
| CL-GOVERNANCE | must | Human plan approval before every build round; agent cannot self-approve | Yes |

**Conflict resolved in ADR-001:** grounding quality (CL-GROUNDING) pulls toward a larger corpus and more retrieved context, while cost (CL-COST) and latency (CL-RESILIENCE) pull toward less. The resolution is top-5 retrieval under a fixed token budget, with abstention when the relevance threshold is not met - never a larger prompt.

**Conflict resolved in ADR-005:** helpfulness (CL-GROUNDING) pulls toward free-form prose, while authority (CL-AUTHORITY) pulls toward structure. The resolution is a constrained JSON contract plus one bounded repair attempt; a second failure becomes a safe fallback.

---

## 3. Boundaries

### 3.1 System boundary

```
Browser (text UI, no secrets)
   | HTTPS, session cookie
   v
AppEntry (HTTP boundary) --> AuthSecurity (identity + ownership) --> AuthRouter
   |
   +--> ProfileSchema
   +--> ChatRouter --> ScopeGuard --> RagPipeline --> RetrievalAdapter --> PostgreSQL/pgvector (published chunks only)
   |                                                   +--> PromptAssembler
   |                                                   +--> Tutor --> hosted LLM / embedding API
   |                                                   +--> CitationValidator (authoritative veto)
   +--> GrammarEvaluator (writing feedback)
   +--> VocabularyLoader / VocabularyService
   +--> ProgressService --> learning_events --> PostgreSQL
   +--> IngestPipeline (offline, reviewer-only) --> content_chunks
```

### 3.2 Trust boundaries

| Boundary | Inside | Outside | Rule |
|---|---|---|---|
| Browser / API | Server session, authorization, secrets | Untrusted user input, client state | The browser never chooses a user_id, never holds a provider key |
| API / model provider | Deterministic validation, policy, persistence | Model output treated as an untrusted proposal | No model output is displayed or persisted before `CitationValidator`; scope control runs before any call |
| API / curriculum corpus | Reviewed, approved content | Learner writing | Retrieval serves only published chunks; learner text never enters the corpus |
| API / database | Owner-scoped repositories, migrations | Direct table access from model code | Only domain services touch repositories; the RAG pipeline has no write path |
| Operator / learner data | Aggregated metrics | Raw learner writing | Stores are owner-scoped; learner text stays in its owner table |

### 3.3 Advisory and authoritative zones

- **Advisory zone:** `Tutor`, `PromptAssembler`, `RagPipeline`, `RetrievalAdapter`. These may propose text and citations. They may not write learner state.
- **Authoritative zone:** `ScopeGuard`, `CitationValidator`, `AuthSecurity`, `ProfileSchema`, `ProgressService`. These decide what is admitted, shown, stored, or served.
- The boundary is crossed in one direction only: advisory proposal -> deterministic scope/validation verdict -> deterministic service action.

---

## 4. Components

One architectural element per module; module and class names are frozen by `docs/code-governance/structural-constraints.md` S1. The 18 modules mirror the SSOT `enforcing_component` paths.

| Element | Responsibility | Module |
|---|---|---|
| `ScopeGuard` | Deterministic intent classification before retrieval/model | `src/backend/safety_boundary/scope_guard.py` |
| `CitationValidator` | Authoritative schema/citation/abstention veto | `src/backend/safety_boundary/citation_validator.py` |
| `SafetyEvaluator` | Grounded-correctness evaluation | `src/backend/safety_boundary/evaluator.py` |
| `RetrievalAdapter` | Conditional, published-only retrieval | `src/backend/ai_companion/retrieval_adapter.py` |
| `RagPipeline` | Proposal-only RAG orchestration | `src/backend/ai_companion/rag_pipeline.py` |
| `Tutor` | Provider adapter, timeout, retry, cost/latency bound | `src/backend/ai_companion/tutor.py` |
| `PromptAssembler` | Layered context within the 1,500-token budget | `src/backend/ai_companion/prompt_assembly.py` |
| `ChatRouter` | Chat HTTP boundary; persists only validated turns | `src/backend/api/routers/chat.py` |
| `ProfileSchema` | Language and CEFR validation | `src/backend/api/schemas/profile.py` |
| `AuthRouter` | Register/login and profile update | `src/backend/auth/router.py` |
| `AuthSecurity` | Session identity and per-record authorization | `src/backend/auth/security.py` |
| `VectorClient` | Read-only vector store access | `src/backend/database/vector_client.py` |
| `GrammarEvaluator` | Writing/grammar feedback | `src/backend/grammar/evaluator.py` |
| `AppEntry` | Composition root; no upload routes | `src/backend/main.py` |
| `ProgressService` | Event-aggregated progress projection | `src/backend/user_progress/service.py` |
| `VocabularyLoader` | Seeded vocabulary selection | `src/backend/vocabulary/loader.py` |
| `VocabularyService` | Familiarity state and review | `src/backend/vocabulary/service.py` |
| `IngestPipeline` | Offline content ingestion | `scripts/ingest_content.py` |

Support packages that are not architectural elements: `src/backend/contracts/` (typed DTOs, ports, enums), `src/backend/db/` (connection, unit of work, repository primitives). They contain no domain decision and are subject to S1-S6 in `structural-constraints.md`.

---

## 5. Authority

| Element | Authority | May override | May never override | Failure if removed |
|---|---|---|---|---|
| `ScopeGuard` | Authoritative admission of a request | Nothing on the request path | Retrieval/model calls | Off-topic prompts reach the model |
| `CitationValidator` | Authoritative veto over model output | Nothing; it is the final gate | Any deterministic service | Unvalidated/citation-free text reaches learners |
| `AuthSecurity` | Authoritative identity and record authorization | Nothing | Any payload or query field | Identity spoofing; cross-user exposure |
| `ProfileSchema` | Authoritative language/level validation | UI defaults | Identity or level checks elsewhere | Invalid profile/level persisted |
| `ProgressService` | Authoritative event log and projections | Cached projections | Any model narrative | Dashboard drift |
| `ChatRouter` | Session owner and turn order | Nothing | `AuthSecurity` | Reassigned or reordered sessions |
| `GrammarEvaluator` | Original-preserving feedback | UI presentation | Original text immutability | Silent overwrite |
| `VocabularyService` | Confirmation and familiarity state | UI suggestions | `AuthSecurity` | Unconfirmed mastery |
| `RetrievalAdapter` | Eligibility filter; advisory relevance | Candidate ranking | Published-only filter | Unpublished/off-level evidence |
| `PromptAssembler` | Advisory assembly | Layer order within ADR-006 | System policy or schema | Budget overflow |
| `Tutor` | Advisory external call and budget enforcement | Retry choice within policy | Safety gate | Unbounded spend |
| `RagPipeline` | Advisory orchestration | Turn routing | Any authoritative element | No proposal, no write |
| `IngestPipeline` | Offline corpus ingestion | Ingest content | Runtime read-only rule | Unapproved content served |
| `AppEntry` | Boundary only; no domain decision | Transport concerns | Authorization or validation | No typed entry point |

**Override rules**

- A model may never override `ScopeGuard`, `CitationValidator`, `AuthSecurity` or `ProgressService`.
- A frontend may never override a progress total, identity or citation.
- A human operator may pause AI features; a human may not bypass the scope or citation gate in a production path.
- Only an accepted ADR plus a human approval may change an authority boundary.

---

## 6. Workflow

| Stage | May do | May not do | Human gate |
|---|---|---|---|
| Plan | Read requirements/ADR/invariants; produce a plan with requirement IDs, files, interfaces, negative tests and rollback | Write `src/`, `frontend/`, `prompts/` or CI | Human approves the plan before any code (`NFR-GOV-001`) |
| Build | Write permitted source, tests and docs; run Tier 1/2 locally | Touch protected paths, approve its own plan, change thresholds | Reviewer confirms approval artifact and AI log entry |
| Verify | Run Tiers 1-3, add tests and evidence, update trace status | Modify `src/` or relax a threshold | Verification evidence linked in the PR |
| Review | Write a review memo with P0/P1/P2 findings and a verdict | Approve its own PR or waive a P0 without an invariant/ADR citation | Named human reviewer signs the memo |
| Release | Deploy the accepted build | Skip Tier 3 or release with an invariant failure | Human release owner approves with a rollback step |

The stage sequence is Plan -> Build -> Verify -> Review -> Release. No stage may run the next stage's actions; an agent that finishes Build does not self-verify a release gate.

---

## 7. Permissions

**Default rule: no read, no write, unless explicitly whitelisted.** The full path table and hook mapping is owned by `docs/architecture/permission-model.md`; this is a summary only.

| Path group | Plan agent | Build agent | Verify agent | Human required? |
|---|---|---|---|---|
| `docs/req/**` | read | read | read | yes - baseline change |
| `docs/architecture/adr/**`, `architecture-blueprint.md` | read | read | read | yes - ADR/blueprint change |
| `docs/architecture/**` registers | read | read/write for status/evidence only | read/write evidence | yes for rule changes |
| `src/backend/safety_boundary/**`, `src/backend/auth/security.py` | read | **no access** | read | yes - human + ADR |
| `src/**` (other modules), `frontend/**`, `scripts/**` | read | write (guarded) | read | plan approval + review |
| `migrations/**` | read | write before first apply; frozen after | read | reviewer + rollback plan |
| `prompts/**`, `content/**`, `.github/workflows/**`, `.opencode/**`, `.agent/**` | read | **no access** | read | yes |
| `test/**` | read | write after test approval | read/write evidence | approval artifact |
| `docs/code-governance/ai-use-log.yaml` | read | append via tool only | read | session owner verifies |
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

**Release thresholds:** citation validity 100% (`NFR-QUAL-003`), retrieval recall@5 >= 0.85 (`NFR-QUAL-001`), grounded correctness >= 0.80 human-scored (`NFR-QUAL-002`), policy escapes 0 (`NFR-SEC-001`), cross-user exposure 0 (`INV-AUTH-001`), off-topic refusal 100% (`NFR-QUAL-004`), p95 turn latency <= 12.0 s (`NFR-PERF-001`), prompt tokens/turn <= 1,500 (`NFR-COST-001`), axe critical violations 0. Thresholds are owned by `requirements.yaml`; this table must not drift from it.

Tier 1 must pass before Tier 2 starts; Tier 2 before Tier 3. No parallelism across tiers. Live evaluation requires controlled credentials and human approval, and fails closed for a release-bound change.

---

## 9. Observability

Operational telemetry is illustrative; R1 has no dedicated observability requirement, so this section names the fields the implementation should emit for debugging and evaluation without over-specifying a schema.

| Field | Example | Purpose |
|---|---|---|
| `request_id` | `req_01J...` | Join API and turn records |
| `user_ref_hash` | `sha256:...` | Per-user cost/abuse detection without identity |
| `task_type` | `conversation`, `lesson_help`, `writing` | Segment quality and cost |
| `model_id` / `prompt_version` | provider id / `prompt_v1.0.0` | Attribute behaviour to a model/prompt |
| `retrieved_chunk_ids` | `["c-0012", "c-0031"]` | Reproduce retrieval and citation validity |
| `validation_result` | `accepted`, `rejected_citation`, `rejected_schema` | Measure the gate |
| `scope_result` | `accepted`, `rejected`, `uncertain`, `mixed` | Measure scope control |
| `latency_ms` | `3120` | SLO tracking (`NFR-PERF-001`) |
| `tokens_in` | `1200` | Cost accounting (`NFR-COST-001`) |
| `outcome` | `answered`, `abstained`, `refused`, `safe_fallback` | Product and safety metrics |

- **Metric convention:** `<domain>_<event>_total` (e.g. `citation_reject_total`, `cross_user_denial_total`, `injection_escape_total`, `progress_mismatch_total`).
- **Alerts:** invariant violation -> CRITICAL; p95 > 12 s for 3 days -> REVIEW; cross-user denial burst > 5 in 10 minutes -> security alert.
- Learner text stays in its owner-scoped store; telemetry carries references and hashes, not raw paragraphs (see ADR-009).

---

## 10. Change policy

| Change | ADR required? | Human approval? | Additional artifact |
|---|---|---|---|
| Bug fix that preserves all contracts and thresholds | No | Reviewer | Regression test + AI log entry |
| Test, docs typo, comment, non-frozen copy edit | No | Reviewer | - |
| New dependency or package | Yes | Yes | Structural constraints module/import update |
| New component, module or authority change | Yes | Yes | Blueprint Section 4, ADR responsibility map, manifest |
| Validation rule or response schema change | Yes | Yes | Invariants, trace matrix, tests, eval replay |
| Threshold or metric change | No, if tightening; yes, if relaxing | Yes | Requirements delta, evaluation logbook row |
| Prompt, corpus, embedding or model change | Yes for scope; version bump required | Yes - content/prompt owner | EVAL-1.0.0 replay evidence |
| Permission change | Yes | Yes | Permission model |
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
  req/{prd.yaml, requirements.yaml, req-schema.json}
  architecture/
    adr/{001-guarded-monolith.md, 005-validated-response-contract.md, 006-layered-context.md,
         007-content-ingestion-and-retrieval.md, 008-event-sourced-progress.md, 009-learner-data-isolation.md,
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
  code-governance/{structural-constraints.md, verification-constraints.md, mcp-tool-manifest.md,
                   ai-use-log.yaml, ai-use-log-schema.json}
  review-memo.md
  debt-register.md
  bug-diary.md
src/backend/             # 18 element modules across safety_boundary/ ai_companion/ api/ auth/ database/ grammar/ user_progress/ vocabulary/ + main.py
src/backend/contracts/   # typed DTOs, ports, enums
src/backend/db/          # connection, unit of work, repository primitives
frontend/                # React + TypeScript learner UI
test/offline/            # deterministic, no network, stub model/retrieval
test/live/               # controlled provider evaluation, credentials required
test/structural/         # import and architecture fitness functions
scripts/                 # validation, trace, permissions, cost, eval runners
migrations/              # ordered SQL migrations
content/                 # reviewed sources, manifest.yaml, vocabulary JSON
evals/                   # EVAL-1.0.0.yaml and fixtures
prompts/                 # versioned prompt files
transcripts/             # annotated agent sessions (humans only)
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
| `.opencode/rules.md`, `.agent/rules.md`, `.opencode/permissions.jsonc` | R1 | Human-only writes; agent read-only |
| `.github/workflows/ci.yml` | R1 | Human-only writes; branch protection depends on it |
| `transcripts/**` | R1 | Append-only raw record; never edited to look better |

**Rules that override convenience:**

- `MUST NOT` modify a frozen directory; frozen paths are listed with the build round they were frozen in.
- `MUST NOT` add a dependency that is not in the module table's `imports from` column.
- `MUST` call the deterministic scope/validation gate after every model output, before any state mutation.
- `MUST` stop for human approval before generating code in a new build round.

---

## Appendix A - Trace to architecture artifacts

| Concern | Owning artifact | Enforcing artifact |
|---|---|---|
| Requirement registry | `docs/req/requirements.yaml` | `scripts/validate_req.py` (planned), CI gate |
| Architecture choice and rejected options | ADR-001, `evaluation-table.md`, `option-ledger.md` | Review |
| Scope and response contract | ADR-005, `invariants.md` INV-SCOPE-001/002, INV-CITE-001 | `ScopeGuard` / `CitationValidator` tests |
| Context layers and token budget | ADR-006 | `PromptAssembler` tests |
| Ingestion and published-only retrieval | ADR-007, `runtime-policy-catalog.md` RP-016 | `IngestPipeline` / `RetrievalAdapter` tests |
| Progress and event records | ADR-008 | `ProgressService` tests |
| Learner data isolation | ADR-009, `memory-design.md` | INV-AUTH-001 tests |
| Agent tool boundary and approvals | ADR-010, `mcp-tool-manifest.md`, `permission-model.md` | hooks and CI gates |
| Configuration | `configuration-governance.md` | config startup tests and S5 |
