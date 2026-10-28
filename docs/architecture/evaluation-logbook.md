# Evaluation logbook - baseline R1

**Rule:** append-only and dated. Each row records one finding, the evidence that produced it, and the artifact the evidence changed. This is the narrative behind the numbers, not a duplicate of the trace matrix.
**Categories:** `candidate review`, `structural`, `guardrail test`, `SEM evaluation`, `incident`, `prompt change`.
**Honesty rule:** no row may imply a test or metric was run when it was not. At baseline the only evidence is documentation analysis and arithmetic; runtime evidence is explicitly marked as absent.

## 1. Log

| # | Date | Category | Finding (measurable statement) | Evidence | Artefact updated |
|---|---|---|---|---|---|
| L-001 | 2026-10-27 | candidate review | C1 Guarded monolith is the only one of four candidates with Strong on all three critical drivers (D1, D2, D7), and has zero Weak cells. | `evaluation-table.md` 40-cell matrix; counts C1 8/2/0, C2 5/5/0, C3 1/8/1, C4 1/6/3 | ADR-001 accepted; `option-ledger.md` C2-C4 rows |
| L-002 | 2026-10-27 | structural | The blueprint has 19 architectural elements, each mapped to exactly one module; 18 requirements are ASR and all 18 name one of those elements. | `requirements.yaml` asr count 18; blueprint §4 19 rows; registry validation 2026-10-27 | `architecture-blueprint.md` §4, `trace-matrix.md` coverage summary |
| L-003 | 2026-10-27 | structural | The fixed context layers sum to 6,200 input tokens, plus a 1,200-token output reserve = 7,400, which is 600 below the 8,000 operational cap. | Arithmetic on ADR-006 §Context layers: 350+300+300+150+200+400+3000+1200+300 = 6,200; +1,200 = 7,400 | ADR-006; ADR-001 layered context table |
| L-004 | 2026-10-27 | candidate review | R1 scope is one language (English for Chinese-speaking learners), text only, with speech, multi-language, teacher portal, payments and web browsing excluded. | `prd.yaml` scope_in/scope_out; `REQ-LANG-ARCH-004` | `requirements.yaml` ARCH-004; blueprint §1 |
| L-005 | 2026-10-27 | guardrail test | The invariant register has 11 rows, each with exactly one source requirement, one enforcing module and a concrete fallback; **zero invariant tests exist yet**, so all 11 remain `declared`. | `invariants.md` summary + detail blocks; repository has no `test/` tree | `invariants.md`; `debt-register.md` DBT-003 |
| L-006 | 2026-10-27 | SEM evaluation | Release thresholds were adopted from the project plan (citation validity 100%, recall@5 >= 0.85, correctness >= 0.80, p95 <= 12 s, cost <= US$0.04); **no baseline measurement has been run**, so these are targets, not results. | `requirements.yaml` fit criteria; `Comprehensive_Project_Plan_version2.md` §3.3 | `requirements.yaml`; risk R-009; `debt-register.md` DBT-001 |
| L-007 | 2026-10-27 | structural | Exactly three gate modules are `no access` for the Build agent (validator, ownership guard, degradation controller); the other invariant-enforcing services are guarded write with a named reviewer. | `permission-model.md` §2; 19 element modules in `structural-constraints.md` | `permission-model.md`; ADR-010; `debt-register.md` DBT-004 |
| L-008 | 2026-10-27 | prompt change | Prompt version `prompt_v1.0.0` is declared as the R1 contract, but `prompts/prompt_v1.0.0.yaml` does not exist yet and no model-facing replay has run. | `configuration-governance.md` `PROMPT_VERSION`; repository `prompts/` absent | ADR-006; risk R-003; `debt-register.md` DBT-007 |
| L-009 | 2026-10-27 | structural | The runtime policy catalog covers 21 paths and all 11 invariants; the two taught paths that do not exist at runtime (evaluator, human review queue) are documented as coverage decisions rather than invented rows. | `runtime-policy-catalog.md` §1, §3, §4; invariant coverage table 11/11 | `runtime-policy-catalog.md`; `debt-register.md` DBT-003 |
| L-010 | 2026-10-27 | guardrail test | The permission table lists 45 rows including the default-deny row; every top-level path in blueprint §11 is covered. Hooks and `permissions.jsonc` are unimplemented, so enforcement is `declared`. | `permission-model.md` §1; blueprint §11 tree | `permission-model.md`; `debt-register.md` DBT-004 |
| L-011 | 2026-10-27 | structural | The risk register has 15 open assumptions, 0 mitigated and 0 closed; every row has a numeric trigger and a named element or gate. | `risk-list.md` §1; status counts | `risk-list.md`; `debt-register.md` DBT-009 |
| L-012 | 2026-10-27 | incident | No incidents have occurred; the project has no runtime. This row is a placeholder for the first incident review and is not evidence of safety. | Repository state at baseline; no deployment | none |

## 2. Threshold relaxations

**None.** No threshold in `requirements.yaml` has been relaxed, and no row is needed under the rule "every relaxed threshold has a logbook row". If a threshold is relaxed later, the row must state the old value, the new value, the evidence and the risk that was accepted.

## 3. Category coverage

| Category | Rows | Notes |
|---|---|---|
| candidate review | L-001, L-004 | Documentation evidence only; no runtime benchmark |
| structural | L-002, L-003, L-007, L-009, L-010, L-011 | Counts and arithmetic, reproducible from the files |
| guardrail test | L-005, L-010 | Static coverage only; no failing test exists yet |
| SEM evaluation | L-006 | Targets adopted; no measured value |
| incident | L-012 | No incident; placeholder |
| prompt change | L-008 | Version declared; prompt file absent |

## 4. Append protocol

1. Add a new row with the next number; never edit or delete an existing row.
2. Date is ISO; category is one of the six exact strings.
3. Finding is one measurable statement, not a narrative paragraph.
4. Evidence is a test id, a command with its result, or an artifact link. "Looks good" is not evidence.
5. Artifact updated names the file whose rule, threshold or status changed as a result.
6. If no artifact changed, the finding is informational; say so explicitly in the last column.
