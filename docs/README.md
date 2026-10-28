# Documentation index - LANG baseline R1

**Project:** AI Language Learning Platform - a grounded English tutor for Chinese-speaking learners.
**Baseline:** R1, 2026-10-27.
**Status:** the **artifact set is complete at documentation level for D1/D2 and specified for D3/D4**; no application code, test, prompt file, evaluation set or CI script exists yet. The gaps are recorded honestly in `debt-register.md` and per-row checkboxes, not assumed away.

## 1. Read in this order

1. `req/requirements.yaml` - what must hold (39 requirements, 9 clusters).
2. `../architecture-blueprint.md` - what may be built, where the walls are.
3. `architecture/adr/` - why this architecture; ADR-001 first, then 005-010.
4. `architecture/invariants.md` - what must never happen.
5. `architecture/trace-matrix.md` - where each requirement is enforced and proven.
6. `architecture/memory-design.md` - what state survives, for how long.
7. `architecture/permission-model.md` - who may read/write which path.
8. `architecture/runtime-policy-catalog.md` - what the system does when X breaks.
9. `code-governance/structural-constraints.md` - how code must be organised.
10. `code-governance/verification-constraints.md` - how evidence is produced.
11. `code-governance/mcp-tool-manifest.md` - which tools may which role call.

The manifest is last because it is derived from the ADR; reading it first invites the agent to treat tools as the design.

## 2. Artifact map and status

| # | File | Answers | Tier | Status at baseline |
|---|---|---|---|---|
| 1 | `req/requirements.yaml` | What and why; how measured | D1 | complete, schema-valid, 39 requirements |
| 2 | `req/req-schema.json` | Is the registry well-formed? | D1 | complete, draft 2020-12 |
| 3 | `req/prd.yaml` | Product intent, scope, journeys, data inventory | D1 | complete |
| 4 | `architecture/adr/001-guarded-monolith.md` | Core architecture choice + responsibility map | CORE | accepted |
| 5 | `architecture/adr/005-validated-response-contract.md` | Server-validated response contract | CORE | accepted |
| 6 | `architecture/adr/006-layered-context.md` | Context layers, budgets, compaction | CORE | accepted |
| 7 | `architecture/adr/007-transactional-publishing.md` | Versioned publish and published-only retrieval | CORE | accepted |
| 8 | `architecture/adr/008-event-sourced-records.md` | Event-sourced progress and server scoring | CORE | accepted |
| 9 | `architecture/adr/009-memory-and-privacy.md` | Checkpoint vs durable memory; retention | CORE | accepted |
| 10 | `architecture/adr/010-agent-tool-boundary.md` | Agent roles, tools, human gates | CORE | accepted |
| 11 | `architecture/invariants.md` | What must never happen | CORE | declared; 11 invariants |
| 12 | `architecture/trace-matrix.md` | Requirement -> enforcement -> evidence | CORE | 39/39 design rows |
| 13 | `architecture/memory-design.md` | State lifetime, ownership, crash semantics | CORE | complete |
| 14 | `architecture/option-ledger.md` | Rejected options + revival conditions | optional | complete |
| 15 | `architecture/permission-model.md` | Path permissions and violation handling | CORE with agents | declared; 45 rows |
| 16 | `architecture/evaluation-logbook.md` | Evidence accumulated | optional | 12 rows, no runtime evidence |
| 17 | `architecture/risk-list.md` | Unproven assumptions | optional | 15 open risks |
| 18 | `architecture/evaluation-table.md` | Why C1 is the best of four candidates | CORE (D2.8) | complete, 40 cells |
| 19 | `architecture/runtime-policy-catalog.md` | Failure and degradation behaviour | optional | 21 policies |
| 20 | `architecture/configuration-governance.md` | Env -> key -> validation; fail loud | D2 (11th type) | complete |
| 21 | `code-governance/structural-constraints.md` | Code organisation and fitness functions | D3 | declared; 6 rules |
| 22 | `code-governance/verification-constraints.md` | Evidence production and gate order | D4 | declared; V1-V4 |
| 23 | `code-governance/mcp-tool-manifest.md` | Tool boundary and allowed callers | D3 | declared; 24 tools |
| 24 | `ai-use-log.yaml` | Agent session evidence | D1 | 0 sessions (empty at baseline) |
| 25 | `review-memo.md` | Was the change acceptable? | D4 | template; no PRs yet |
| 26 | `debt-register.md` | What are we paying interest on? | D4 | 10 open rows |
| 27 | `bug-diary.md` | What did each defect teach? | D4 | template; no bugs yet |

Root `architecture-blueprint.md` is one of the 11 D2 artifact types and sits at the repository root as required.

## 3. Canonical facts

| Fact | Value |
|---|---|
| Project code | `LANG` |
| Requirement IDs | `REQ-LANG-<TYPE>-NNN` |
| Requirement count | 39 (36 `must`, 3 `should`; 18 ASR) |
| Architectural elements | 19, one module each |
| Invariants | 11 (`INV-001`..`INV-011`) |
| ADRs | 001, 005-010 accepted; 002-004 reserved for rejected candidates |
| Runtime policies | 21 (`RP-001`..`RP-021`) |
| Risks | 15 (`R-001`..`R-015`), all open |
| Debt | 10 (`DBT-001`..`DBT-010`), all open |
| Tools | 14 runtime + 10 agent = 24 |
| Evaluation set | `EVAL-1.0.0`, 64 cases (24 grounded + 16 abstention + 24 adversarial) |
| Reference thresholds | citation 100%, recall@5 >= 0.85, correctness >= 0.80, p95 <= 12 s, cost <= US$0.04, axe 0 critical |
| Target release | one language (English for Chinese speakers), text only, 12 lessons / >= 80 chunks, 300 vocabulary entries |

## 4. Consistency rules

| If you change... | You must also update... | Checked by |
|---|---|---|
| a requirement ID | trace matrix, test docstrings, ADR related-requirements | `check_trace.py` (planned) |
| a threshold | `requirements.yaml`, `verification-constraints.md`, runtime policy escalation | grep for the number |
| an element name | blueprint §4, ADR-001 map, module table, manifest callers | name check (planned) |
| a module path | module table, permission model, frozen list | diff of tables (planned) |
| an invariant | invariants register, trace matrix, runtime policies, manifest | link check (planned) |
| a frozen path | `AGENTS.md` scope table, permission model, structural constraints | CI gate (planned) |
| a prompt version | prompt file, AI log entry, evaluation replay set | log/eval gate (planned) |

No threshold is duplicated with a different value. Where a number appears in more than one file, the requirements file is the owner and the other file must match it exactly.

## 5. Validation commands (what will run)

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

At baseline only the following can be checked: YAML parse, JSON parse and JSON Schema validation of `requirements.yaml`. Everything else is specified but not implemented.

## 6. Known gaps (read before trusting a green checkbox)

1. **No code or tests.** All 39 trace rows are `design`; all 11 invariants are `declared`; no gate script exists (`DBT-002`, `DBT-003`).
2. **No evaluation set or prompt file.** `EVAL-1.0.0` and `prompt_v1.0.0` are named contracts, not files (`DBT-001`, `DBT-007`).
3. **No permissions hooks or dispatcher.** The 45-row permission model and 24-tool manifest are enforced by review only (`DBT-004`, `DBT-005`).
4. **No CI.** `.github/workflows/ci.yml` is empty; the canonical commands are not wired (`DBT-002`).
5. **No names/student IDs.** Members are role labels until Sprint 1 confirms names (`prd.yaml` Q-001).
6. **Root instruction files are empty.** `AGENTS.md`, `Prompt.md`, `README.md` and `Report.md` are empty at baseline; the reading order is present here and in the blueprint, but the root agent instructions and submission report still need to be written.

## 7. How to change a baseline

1. Do not silently edit a frozen file. Add a new ADR (supersede, do not rewrite) for an architecture decision.
2. For a requirement change, append an `R2` delta block to `requirements.yaml` with `added` / `modified` / `obsoleted` and a trigger; never reuse an ID.
3. Append rows to the trace matrix, invariant register, risk list and logbook; never delete history.
4. Update the consistency table above in the same PR; a reviewer checks the numbers, not the prose.
5. Record the change in `ai-use-log.yaml` as a new session entry and in `evaluation-logbook.md` with the evidence that justified it.
