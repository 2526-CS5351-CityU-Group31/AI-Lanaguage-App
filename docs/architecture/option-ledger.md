# Option ledger - baseline R1

**Purpose:** record what was rejected, on which failed criterion, and the event that would make it viable again. Silence is how a team re-litigates the same decision every sprint.
**Owner:** Member 3 (Backend & Data); reviewed by Members 1, 2, 5.
**Related:** `evaluation-table.md`, ADR-001, `risk-list.md` R-006, `runtime-policy-catalog.md`.

## 1. Rejected architecture candidates

Reserved ADR IDs are intentional. ADR-002, ADR-003 and ADR-004 are **not missing files**; they are reserved so a revival does not collide with an unrelated decision.

| ID | Option | Strengths (stated fairly) | Risks / costs | Why rejected (failed criterion) | Conditions for reconsideration | Status | Reserved ADR |
|---|---|---|---|---|---|---|---|
| C2 | Split retrieval service | Retrieval scales and deploys independently; a retrieval failure is isolated from the API; a separate vector store can be tuned without touching the domain | A second deployable, HTTP contract, network failure mode, duplicate backup, offline test stubs that can drift, ops effort | Testability (D7): critical retrieval/validation path becomes a cross-process contract; complexity (D9) Medium for a 1k-chunk corpus | Retrieval p95 > 800 ms for 2 consecutive weeks at production volume **or** corpus > 100,000 chunks **or** sustained > 50 rps for one week | **Deferred** (not permanently rejected) | ADR-002 |
| C3 | Managed RAG/agent platform | Fast integration; vendor handles retrieval availability and scaling; less retrieval ops for a small team | Vendor lock, residency and sub-processor review, opaque retrieval/prompt internals, partial authority and testability, unpredictable cost | Authority separation (D2) and testability (D7): vendor orchestration is not locally reproducible and policy control is partial | Team retrieval-ops capacity < 0.5 FTE for 2 sprints **and** the vendor offers regional residency, published-only filtering, replayable evaluation and full data export | **Deferred** | ADR-003 |
| C4 | Agentic tutor with database tools | Flexible context gathering; fewer bespoke read modules; can answer novel questions | Every prompt becomes an attack surface; write tools make the authority boundary unprovable; tool sandbox and adversarial evaluation exceed the schedule | Invariant protection (D1) and authority separation (D2): the model can mutate state; a post-hoc validator cannot unfire a write | Only after a new architecture round and ADR that (a) makes every tool read-only, (b) proves a pre-write gate, (c) sandboxes the dispatcher, (d) passes 24/24 adversarial cases and 20/20 ownership probes, with a two-reviewer security sign-off | **Permanently rejected for R1** | ADR-004 |
| C5 | No-LLM static lesson library | Deterministic, cheap, no provider risk; strong grounding by construction | Not interactive tutoring; fails the product premise and the AI-component requirement | Fit to scope / product premise: no conversational practice or adaptive feedback | Not an architecture candidate. If the AI budget is removed, it is a degraded mode (`RP-008`), not a replacement architecture | **Not evaluated** | none in this domain |

**Reading the statuses:** C2 and C3 are deferred with numeric triggers; C4 is permanently rejected for R1 because its failure is structural, not a matter of tuning; C5 is recorded so nobody re-proposes it as though it were never considered.

## 2. Rejected design options inside C1

These are smaller decisions made during the baseline. Each names the failed rule and what would revive it. The owning ADR is the authority if this table and the ADR disagree.

| Option | Failed criterion | Why it lost | Status | Reconsideration trigger | Owning ADR |
|---|---|---|---|---|---|
| Free-form prose responses with regex checks | Invariant protection / provenance | A regex cannot prove a quoted lesson exists in the retrieved published set | Rejected | None; a new contract must pass the same validator tests | ADR-005 |
| Model self-critique of its own citations | Authority separation | The same model is not an independent gate and can rationalise an invented source | Rejected | A separately governed verifier with its own model and evidence, added by ADR | ADR-005 |
| Two-model critic in R1 | Cost and latency | Doubles spend and adds a non-deterministic judge without a deterministic gate | **Deferred** | Cost per session <= US$0.02 with the critic included, and citation validity stays 100% in a trial | ADR-005 |
| Two-model critic for pedagogy quality | Quality evidence | A model judge is not ground truth for pedagogy; human scoring is required | Deferred | If human review capacity < 2 reviewers per release, a model judge may *triage*, never decide | ADR-005 |
| Post-filtering after top-k retrieval | Published-only proof | An unpublished chunk can influence ranking before it is filtered | Rejected | None; pre-filter is a hard rule (`ARCH-003`) | ADR-007 |
| In-place corpus edits | Reversibility / provenance | A half-updated lesson can serve mixed sections and cannot be rolled back | Rejected | None; a version switch is the only publish path | ADR-007 |
| Full transcript in every prompt | Cost, latency, privacy | Unbounded context and longer retention in provider requests | Rejected | A context window > 10x the current budget plus a cost model that stays under US$0.04 | ADR-006 |
| Silent truncation of old turns | Continuity and inspectability | The learner cannot see or correct what was forgotten | Rejected | None; compaction must write an inspectable summary | ADR-006 |
| Denormalised progress counters | Invariant protection / parity | A lost update or retry drifts the total with no source of truth | Rejected | A cache with a same-request parity check and an event-sourced backfill (allowed only as a cache) | ADR-008 |
| Client-computed quiz score | Authority / isolation | The client is untrusted; a forged score becomes a record | Rejected | None | ADR-008 |
| External memory service | Testability and privacy | Another processor and network contract for state PostgreSQL can hold | Rejected | A managed service with regional residency, deletion SLA and offline contract tests, after an ADR | ADR-009 |
| Vendor-managed thread state | Reproducibility | Context cannot be reconstructed from our own records | Rejected | Vendor exposes a full, exportable turn log with versions | ADR-009 |
| Agent self-approval of its own plan | Authority separation | Planner and approver become the same principal | Rejected | None | ADR-010 |
| Unrestricted shell/file access for agents | Enforcement | A protected path is protected only by the model's willingness to obey | Rejected | None; every mutation goes through a named tool | ADR-010 |
| Model-generated progress narrative | Record integrity | A narrative cannot be audited or recomputed | Rejected | None | ADR-008 |

## 3. Conditions that would reopen the chosen architecture

| Event | Threshold | What reopens |
|---|---|---|
| Retrieval latency | p95 > 800 ms for 2 consecutive weeks | C2 viability review (ADR-002) |
| Corpus growth | > 100,000 published chunks | C2 viability review |
| Request volume | > 50 rps sustained for one week | C2 viability review |
| Hosting constraint | Managed PostgreSQL lacks pgvector at the selected plan | ADR-007 reopened; C2/C3 scored again |
| Vendor requirement | Team ops capacity < 0.5 FTE for 2 sprints, vendor meets residency/replay conditions | C3 viability review (ADR-003) |
| Safety incident | Any invariant bypass or cross-user exposure | ADR-001, ADR-005 and the invariant register reviewed before any feature work |
| Cost drift | 7-day mean session cost > US$0.04 | ADR-006 budget and ADR-005 output cap reviewed |

## 4. Rule for adding a row

- Every candidate scored in `evaluation-table.md` has a row here (except the chosen C1).
- Every rejected option that was not scored - because it failed the product premise - still gets one line; "obviously invalid" is a reason, not a reason to omit it.
- A reconsideration condition must contain a number, an event and an owner. "When needed" is not a condition.
- Reviving an option requires an ADR that cites this row and the evaluation table, not an edit to this ledger that silently removes the rejection.
