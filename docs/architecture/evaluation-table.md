# Architecture candidate evaluation - baseline R1

**Question:** given four candidate architectures and ten dimensions, why is C1 chosen - and on which dimensions does it lose?
**Decision owner:** Member 3 (Backend & Data); reviewers Members 1, 2, 5.
**Consumers:** ADR-001 (Alternatives and Rationale), `option-ledger.md`, the report's architecture section.
**Frozen:** 2026-10-27, baseline R1.

> **Scoring discipline.** The observable rules below were fixed before scores were assigned, and every cell must be justifiable by its rule. The rules and the matrix were authored in one documentation pass (no earlier scoring commit exists); the rules are therefore the contract, and a disputed cell must be re-derived from its rule, not argued from preference. This is stated explicitly to satisfy the "scoring rules before scores" check - the evidence is the rule text, not a commit timestamp.

## 1. Dimensions and observable scoring rules

Ten dimensions, adapted from the taught set. "Strong" is always the better outcome for the project; for implementation complexity, "Strong" means **low** complexity, because complexity is a cost, not a quality.

| # | Dimension | Weak | Medium | Strong | Critical? |
|---|---|---|---|---|---|
| D1 | Invariant protection | Model output can reach display or state without a server-side gate | A gate exists but at least one path crosses a process or vendor boundary, or a path can bypass it | Every model output passes one server-side gate inside the same trust boundary on all display and write paths; a static test proves no alternate path | **Yes** |
| D2 | Authority separation | The model can mutate learner state (tools or generated records) | The model has read-only tools or vendor-managed orchestration; writes still pass through code | The model has no read or write tools and returns only a proposal; every write is made by a deterministic service | **Yes** |
| D3 | Explanation isolation | Generated text is the record (progress, score or feedback) | Generated and authoritative data share a table or path, separated by flags | Generated explanations and citations are stored separately and can never determine a score, total or authorization decision | No |
| D4 | Availability | A failure yields a 500, partial state, or unsafe fallback | Fallbacks are defined, but a single component has no redundancy or graceful path | Every failure path has a defined safe action and no single component is without a fallback or SLA | No |
| D5 | State / review continuity | No durable state; a turn cannot resume | Checkpoint or summary exists, but lease, idempotency or scope is missing | Checkpoint + lease + idempotency + a bounded user-scoped summary, all owner-scoped | No |
| D6 | Observability | Only application logs; no per-turn versions or validation result | Partial telemetry; reconstructing a turn requires a cross-service join | One per-turn record with request id, model/prompt/corpus versions, validation result, latency, tokens and cost | No |
| D7 | Testability | Critical paths need a live vendor or are non-deterministic | Critical paths cross a process or network contract that must be stubbed | All critical paths are testable offline in one process with deterministic model and retrieval stubs | **Yes** |
| D8 | Modifiability | A corpus, prompt or model change requires a rewrite | Versioned, but co-deployed with the API; change blast radius is the whole system | Corpus, index, prompt and model are independently versioned and swappable behind interfaces | No |
| D9 | Implementation complexity (cost) | > 5 deployable units or bespoke orchestration | 4-5 deployable units, or one extra managed service beyond API + DB + frontend | <= 3 deployable units (API + DB + frontend) and no infrastructure beyond PostgreSQL | No |
| D10 | Fit to scope | Exceeds the 5-sprint, 5-person, text-only single-language scope | Needs one extra specialist, vendor dependency or operational burden | Fits one team, five sprints, one language, text-only, with no new specialist | No |

**Critical-driver rule:** a candidate is eligible only if it scores **Strong** on all three critical drivers (D1, D2, D7). A higher total score does not compensate for a Medium or Weak on a critical driver. This is the deck's rule applied literally: critical drivers decide, totals do not.

## 2. Candidates

| ID | Candidate | One-line description | Status |
|---|---|---|---|
| C1 | Guarded monolith | One FastAPI API + PostgreSQL/pgvector; model advisory behind one validator; retrieval behind a port | **Chosen (ADR-001)** |
| C2 | Split retrieval service | Same API and validator, but retrieval runs as a separate service with its own HTTP contract and vector store | Rejected; ADR-002 reserved |
| C3 | Managed RAG/agent platform | Vendor-hosted retrieval and orchestration behind an adapter; local API validates the final response | Rejected; ADR-003 reserved |
| C4 | Agentic tutor with database tools | Model calls read/write tools through a tool dispatcher to fetch context and persist records | Rejected; ADR-004 reserved |

## 3. Score matrix

Each cell is a score plus a one-line observable reason. No bare letters. No empty cells.

| Dimension | C1 Guarded monolith | C2 Split retrieval | C3 Managed RAG/agent | C4 Agentic DB tools |
|---|---|---|---|---|
| D1 Invariant protection (critical) | **S** - one process, one gate, one import contract; no alternate display or write path | **S** - the API still owns the gate; the retrieval service is read-only and returns evidence | **M** - the API validates, but vendor orchestration can inject context and tool calls outside the local evidence set | **W** - the model calls mutating tools; a post-hoc validator cannot unfire a write |
| D2 Authority separation (critical) | **S** - model returns a typed proposal; no tools; every write is a domain service | **S** - same proposal contract; retrieval service has no write API | **M** - vendor agent controls retrieval/generation flow and may hold state the team cannot inspect | **W** - model holds DB tools; authority collapses into the prompt |
| D3 Explanation isolation | **S** - suggestions and citations live separately; scores and totals come only from events | **S** - same separation; retrieval is read-only | **M** - vendor-managed citations and summaries make the boundary harder to prove | **M** - generated text and records can occupy the same path unless each tool is separately guarded |
| D4 Availability | **M** - one API is a single point of failure, though every failure has a safe fallback | **M** - an extra service adds a failure mode; fallbacks exist but the contract is larger | **S** - managed SLA for retrieval/generation, though an outage still removes AI features | **M** - tool failures can leave partial state; retries are defined but the path is complex |
| D5 State / continuity | **S** - checkpoint + lease + idempotency + bounded summary, all local | **S** - the same state design in the API; retrieval is stateless | **M** - vendor thread state plus a local summary: two sources of truth to reconcile | **M** - model context and tool-call state are not a durable checkpoint |
| D6 Observability | **S** - one audit row per turn with all versions, validation, latency and cost | **M** - a turn requires joining API and retrieval-service telemetry | **M** - vendor dashboard is partial; internal reconstruction needs provider exports | **M** - tool calls can be logged, but the decision path is distributed across model turns |
| D7 Testability (critical) | **S** - all critical paths testable offline in one process with deterministic stubs | **M** - the offline suite must stub an HTTP contract that can drift from the deployed service | **W** - live vendor required for realistic behaviour; replay is not reproducible | **M** - tools can be faked, but tool selection and multi-turn behaviour are non-deterministic |
| D8 Modifiability | **M** - corpus/prompt/model are versioned, but the API and validator deploy together | **S** - retrieval can be changed, scaled and deployed independently | **M** - vendor configuration is easy, but prompt/retrieval internals are opaque | **M** - adding a tool is easy; every addition needs a safety review |
| D9 Implementation complexity (cost) | **S** - API + DB + frontend; no extra infrastructure | **M** - one more deployable, network contract, indexing deployment and backup | **M** - vendor service plus API + DB + frontend; integration and procurement work | **S** - fewer modules to build, but the safety review is not counted as code |
| D10 Fit to scope | **S** - one team, five sprints, one language, text-only; no new specialist | **M** - needs ops effort for a second service the corpus size does not justify | **M** - vendor cost, residency and curriculum control need review; less fit for a course demo | **W** - a tool sandbox and security review exceed the R1 scope and schedule |
| **Counts (S / M / W)** | **8 / 2 / 0** | **5 / 5 / 0** | **1 / 8 / 1** | **1 / 6 / 3** |

## 4. Tradeoff summary

| Candidate | Main advantage | Main cost | When appropriate |
|---|---|---|---|
| C1 Guarded monolith | Only candidate Strong on all three critical drivers; one provable gate; offline testability | Single deployable; retrieval cannot scale independently | R1 with a small corpus and a five-person team (chosen) |
| C2 Split retrieval | Independent retrieval scaling and deployability | Cross-process testability drift; second service to operate | Retrieval p95 > 800 ms for 2 weeks, or corpus > 100,000 chunks, or request volume > 50 rps |
| C3 Managed RAG/agent | Fast to integrate retrieval; vendor handles availability | Authority and testability are partly delegated; vendor lock, residency and cost | Team lacks retrieval ops **and** the vendor offers regional residency, published-only filters and replayable evaluation |
| C4 Agentic DB tools | Flexible, fewer bespoke modules | Collapses authority; write tools make every prompt an attack surface | Not appropriate for R1; only revisit after a new ADR that makes all tools read-only and proves a pre-write gate |

## 5. Decision basis

1. **Critical drivers are D1 invariant protection, D2 authority separation and D7 testability.** They are critical because the product's trust claim and the course's offline evidence both depend on them; a candidate that fails one cannot be rescued by a better score elsewhere.
2. **C1 is the only candidate that scores Strong on all three critical drivers.** C2 ties C1 on D1 and D2 but scores Medium on D7; C3 scores Medium, Medium, Weak; C4 scores Weak, Weak, Medium.
3. **The winner is not chosen by total score.** C2 has a respectable 5 Strong cells, but its Medium on a critical driver disqualifies it. A weighted sum would hide exactly the failure the scoring rule exists to expose.
4. **C1 has no Weak cell.** Its two Medium cells (availability, modifiability) are accepted with named mitigations: fallbacks and readiness for availability; versioning and the `RetrievalPort` seam for modifiability, with C2 as the pre-approved revival path.
5. **The conclusion is quoted verbatim in ADR-001:**

> **"C1 is the only candidate that scores Strong on all three critical drivers - invariant protection, authority separation and testability - and it does so without a Weak cell in any dimension."**

## 6. Assumptions behind the scores

| Assumption | Value used | If false |
|---|---|---|
| Corpus size at R1 | ~1,000 chunks (12 lessons, >= 80 chunks, plus vocabulary) | C2 becomes more attractive above 100,000 chunks (`R-006`) |
| Team | 5 part-time members, 5 sprints | A smaller team strengthens C1; a larger ops team could make C2 viable |
| Provider | Hosted LLM with structured output, 25 s timeout | A provider without structured output weakens C1's D1/D7 until a validator adapter exists |
| Hosting | One managed PostgreSQL with pgvector | If pgvector is unavailable, reopen ADR-007 and re-score C2/C3 (`R-006`) |
| Evidence standard | Offline deterministic suite required for critical paths | If only live evaluation were accepted, D7's rule would change and the table must be re-derived |

## 7. Done-when status

- [x] Every candidate is scored on every dimension (40 cells, no empty, no unexplained N/A).
- [x] The scoring rules are stated before the matrix and are observable.
- [x] The chosen candidate's Weak cells: none; its two Medium cells have mitigations and linked risks (`R-002`, `R-006`).
- [x] The conclusion is quoted verbatim in ADR-001's rationale.
- [x] Every rejected candidate has a row in `option-ledger.md` with a numeric reconsideration condition.

## 8. Re-derivation rule

If a reviewer disputes a cell, re-derive that single cell from the Section 1 rule and record the change in `evaluation-logbook.md` with the date and reason. Do not adjust a total to make a preferred candidate win; a change to a critical-driver rule invalidates the comparison and requires a new evaluation table version.
