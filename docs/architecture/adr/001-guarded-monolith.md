# ADR-001: Adopt a guarded monolith with an AI-advisory tutor for the R1 learner platform

- **Status:** Accepted
- **Date:** 2026-10-27
- **Supersedes:** -
- **Superseded by:** -
- **Decision owner:** Member 3 (Backend & Data), co-signed by Member 2 (AI & RAG)
- **Related requirements:** INV-SCOPE-001, INV-SCOPE-003, INV-SCOPE-006, INV-AUTH-001, INV-SEC-001, INV-SEC-002, INV-CITE-001, INV-PROG-001, NFR-SEC-001, NFR-QUAL-001, NFR-QUAL-003, NFR-PERF-001, NFR-COST-001, FR-CHAT-001, FR-RAG-001, FR-FEED-001, FR-DASH-001, NFR-GOV-001, NFR-GOV-002
- **Related artifacts:** `architecture-blueprint.md` §4-§5, `docs/architecture/invariants.md`, `docs/architecture/evaluation-table.md`, `docs/architecture/option-ledger.md`, `docs/architecture/memory-design.md`, `docs/architecture/runtime-policy-catalog.md`, `docs/code-governance/structural-constraints.md`, `docs/code-governance/mcp-tool-manifest.md`. The code modules, tests and runtime monitors for this decision are enumerated in the responsibility map below and in `trace-matrix.md`.
- **Review triggers:** `citation_reject_total > 0`; `policy_escape_count > 0`; `validation_reject_rate > 5%` in any rolling week; `tutor_response_p95_seconds > 12` for 3 consecutive days; retrieval `p95 > 800 ms` for 2 consecutive weeks; corpus `> 100,000` published chunks; authenticated request volume `> 50 rps` sustained for one week; a new provider or deployment topology is proposed; any accepted ADR that changes an authority boundary.

> **Reserved IDs:** ADR-002, ADR-003 and ADR-004 are reserved for the three rejected candidates C2, C3 and C4 in `docs/architecture/option-ledger.md`. They are intentionally not written; a reconsideration condition must be met and an ADR opened before any of those options returns.

## Context

R1 must deliver a working learner platform in five sprints with five part-time team members. The forces are in direct tension:

- **Authority (CL-AUTHORITY).** The product claim is that AI feedback is trustworthy and learner records are real. That requires a server-side gate that no model path can bypass, and no database write reachable from model text.
- **Grounding (CL-GROUNDING).** Answers about taught rules must cite published curriculum sections, or abstain. The corpus is small (12 lessons, >= 80 chunks), reviewed by two people, and versioned.
- **Isolation (CL-ISOLATION).** Every record read and write must be scoped to the authenticated learner, including negative tests for cross-user access.
- **Cost and latency (CL-COST, CL-RESILIENCE).** Context assembly must stay within a strict 1,500 prompt-token ceiling per turn (`NFR-COST-001`) and a turn must meet the 12 s p95 latency target (`NFR-PERF-001`). Every additional deployable unit adds operational work the team does not have.
- **Testability.** The safety claims must be provable offline, without provider credentials, in a fresh checkout.

The architectural question is therefore not "how do we build a tutor?" but "where do we put the validation and authorization boundary so that four different candidates can be compared on the same criteria?"

## Decision

Adopt a **guarded monolith**: one FastAPI backend and one PostgreSQL database (with pgvector) host the learner domain, retrieval and validation; the hosted LLM is called inside the `Tutor` adapter, and its output is treated as an untrusted proposal that only `CitationValidator` (and the `ScopeGuard`) can accept or veto.

The model is advisory. Deterministic code is authoritative. `RagPipeline` orchestrates retrieval, context assembly, the model call and validation, but has no write path; `ChatRouter` persists a turn only after a deterministic validation verdict and scope result.

## Rationale

The decision is not "a monolith is simpler". It is that a single deployable unit is the only candidate that makes the authority boundary *locally provable* without adding a second trust boundary the team cannot test.

- One process means one validation gate and one import contract. A static check can prove that `CitationValidator` is reachable only from `RagPipeline`, and that `RagPipeline` imports no database module.
- One database means a turn and its audit event can commit in one transaction, and a content publication can switch versions atomically without a distributed protocol.
- Retrieval stays behind `RetrievalAdapter`, so the split-service option remains available at the same seam if scale ever justifies it.
- The model has no tools. The only "tool" it influences is a typed proposal that a deterministic validator inspects.

The candidate comparison is owned by `docs/architecture/evaluation-table.md`. Its conclusion is quoted verbatim:

> **"C1 is the only candidate that scores Strong on all three critical drivers - invariant protection, authority separation and testability - and it does so without a Weak cell in any dimension."**

## Alternatives considered

| Option | Failed criterion | Evidence |
|---|---|---|
| C2 - Split retrieval service (separate vector service behind HTTP) | Testability: the critical retrieval and validation path becomes a cross-process contract, so the offline suite must stub a network boundary and can drift from the deployed contract | `docs/architecture/evaluation-table.md` column C2; `option-ledger.md` C2 |
| C3 - Managed RAG/agent platform (vendor-hosted retrieval and orchestration) | Testability and authority separation: vendor orchestration is not reproducible offline, and prompt/policy control is partially delegated | `docs/architecture/evaluation-table.md` column C3; `option-ledger.md` C3 |
| C4 - Agentic tutor with database tools | Invariant protection and authority separation: a model with read/write tools collapses the advisory/authoritative boundary regardless of prompting | `docs/architecture/evaluation-table.md` column C4; `option-ledger.md` C4 |
| C5 - No-LLM static lesson library | Not scored: it fails the product premise (interactive tutoring) before architecture criteria apply | `option-ledger.md` "not evaluated" |

C2 is not a bad design; it is the right design at a scale the team does not have. Its reconsideration condition is recorded with a number, not a preference.

## Consequences

**Benefits**

- One deployable unit, one database, one validation gate: the smallest surface that can satisfy CL-AUTHORITY and CL-ISOLATION at the same time.
- Offline tests can exercise the real pipeline with stub model and retrieval adapters; no network contract to mock.
- A turn, its learning events and its audit record can be written in one transaction.
- The retrieval seam (`RetrievalAdapter`) preserves the option to split later without rewriting the RAG pipeline.

**Costs**

- The API is a single point of failure; a process crash interrupts every learner flow. Mitigated by health/readiness endpoints, safe restart and the runtime policy catalog, not by high availability in R1.
- Model, retrieval and API latency share one process resource pool; a slow provider consumes worker time. Mitigated by bounded timeouts and a circuit breaker in the `Tutor` adapter.
- A monolith invites cross-module imports. This is contained by the import-linter contracts and single-writer rules in `structural-constraints.md`, not by good intentions.
- Scaling retrieval independently is impossible without the C2 split; accepted until a review trigger fires.

## Responsibility map

| Element | Responsibility | Implemented in |
|---|---|---|
| ScopeGuard | Deterministic intent gate before retrieval/model | `src/backend/safety_boundary/scope_guard.py` |
| CitationValidator | Authoritative citation/output veto | `src/backend/safety_boundary/citation_validator.py` |
| SafetyEvaluator | Grounded-correctness evaluation | `src/backend/safety_boundary/evaluator.py` |
| RetrievalAdapter | Conditional, published-only retrieval | `src/backend/ai_companion/retrieval_adapter.py` |
| RagPipeline | Proposal-only RAG orchestration | `src/backend/ai_companion/rag_pipeline.py` |
| Tutor | Provider adapter, retry, cost and latency bound | `src/backend/ai_companion/tutor.py` |
| PromptAssembler | Layered context and token budget | `src/backend/ai_companion/prompt_assembly.py` |
| ChatRouter | HTTP chat boundary; persists only validated turns | `src/backend/api/routers/chat.py` |
| ProfileSchema | Language and CEFR validation | `src/backend/api/schemas/profile.py` |
| AuthRouter | Register/login and profile update | `src/backend/auth/router.py` |
| AuthSecurity | Session identity and per-record authorization | `src/backend/auth/security.py` |
| VectorClient | Read-only vector store access | `src/backend/database/vector_client.py` |
| GrammarEvaluator | Writing/grammar feedback | `src/backend/grammar/evaluator.py` |
| AppEntry | Composition root; no upload routes | `src/backend/main.py` |
| ProgressService | Event-aggregated progress projection | `src/backend/user_progress/service.py` |
| VocabularyLoader | Seeded vocabulary selection | `src/backend/vocabulary/loader.py` |
| VocabularyService | Familiarity state and review | `src/backend/vocabulary/service.py` |
| IngestPipeline | Offline content ingestion | `scripts/ingest_content.py` |

## Quality attribute tradeoffs

| Attribute | Tactic | Buys | Costs | Metric that would invalidate |
|---|---|---|---|---|
| Safety / invariant protection | Single validation gate; model has no tools; fail closed | A provable one-way data flow | A validator failure ends the turn instead of degrading to partial text | `validation_bypass_count > 0` |
| Security / isolation | Principal from session only; every repository call owner-scoped | Cross-user exposure is testable at one boundary | An extra authorization query per access | `cross_user_exposure_count > 0` |
| Grounding | Citation validation against retrieved IDs; abstention | No fabricated curriculum authority | Lower answer coverage on out-of-corpus questions | `citation_validity < 100%` or `recall@5 < 0.85` |
| Performance | Top-5 retrieval; fixed prompt-token budget; provider timeout; bounded retries | Predictable latency and cost | Shorter answers and less history | `p95 > 12 s` for 3 days |
| Availability | Health/readiness, circuit breaker on the provider, safe fallback, retry state | Safe failure instead of corrupt state | AI features pause when the provider or budget fails | `safe_fallback_rate > 10%` for 3 days |
| Modifiability | Corpus/index/prompt/model versioned; `RetrievalAdapter` seam | Changes are measurable and reversible | Every model-facing change runs EVAL-1.0.0 | `eval_gate_coverage < 100%` |
| Implementation cost | One API, one database, one frontend | Team can deliver a working demo | No independent scaling; one deployment | `session_cost_usd > target` or schedule slip > 1 sprint |
| Accessibility | Server-rendered structure, labelled controls, keyboard-first flows | Five critical journeys testable with axe | More frontend effort than a chat box | `axe_critical_violations > 0` |

## Layered context design (summary - details owned by ADR-006)

Context assembly is layered within a **strict total prompt-token ceiling of 1,500 tokens per turn** (owned by `NFR-COST-001` and ADR-006), with automated history compaction after six messages. The exact per-layer caps, assembly pipeline and compaction rules are defined once in ADR-006; this ADR does not duplicate them, to prevent two conflicting budget tables.

## Done-when checks for this ADR

- [x] Every `FR-`/`INV-`/`NFR-` named here exists in `requirements.yaml` and is listed in `trace-matrix.md`.
- [x] Every rejected alternative has a named failed criterion, not an adjective.
- [x] Every review trigger is an expression a monitor or reviewer can evaluate.
- [x] The responsibility map matches the module table in `structural-constraints.md` one-for-one (18 modules).
- [ ] The decision has been exercised by an implemented offline test suite - tracked as `DBT-003` until Sprint 3.

## Change log

| Date | Change | Evidence |
|---|---|---|
| 2026-10-27 | Initial decision accepted at baseline R1 | `docs/architecture/evaluation-table.md`, `evaluation-logbook.md` 2026-10-27 |
