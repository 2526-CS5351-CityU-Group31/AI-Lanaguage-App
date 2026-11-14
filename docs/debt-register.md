# Debt register - baseline R1

**Purpose:** record what the project is already paying interest on, in the categories that AI-generated code specifically creates, and rank by interest x blast radius (not by age).
**Owner:** Member 5 (QA & Governance); each row has a named owner.
**Status:** all rows `open`; none has been paid. A paid row is `closed` with the commit that paid it.

## 1. Category definitions

| Category | What it looks like in LANG |
|---|---|
| Prompt rot | A prompt version referenced by config or an ADR but not present, or superseded without an eval replay |
| Hallucinated dependencies | Imports, scripts or packages referenced by docs or code that do not exist or are unused |
| Untouchable code | A module nobody can safely change (human-only gate code with no named author, or opaque generated code) |
| Hidden dependencies | Undeclared coupling: a shared global, implicit ordering, a service importing a store it does not own |
| Agent-induced bloat | Duplicated helpers, dead branches, redundant abstractions produced by repeated agent passes |
| Evaluation debt | A threshold with no evaluation set, or a test that cannot fail |
| Guardrail debt | An invariant enforced in prose but not code, or a permission rule with no hook |
| Human/cognitive debt | A rule only one person can explain, or a review gate with no backup reviewer |

## 2. Register

| ID | Category | Location | Symptom | Interest (per sprint) | Evidence | Trigger to pay down | Owner | Status | Linked ADR/INV/risk | Rank |
|---|---|---|---|---|---|---|---|---|---|---|
| DBT-001 | Evaluation debt | `evals/`, `scripts/run_eval.py` (absent) | EVAL-1.0.0, the replay runner and the human-scoring rubric do not exist; all quality thresholds are unmeasured targets | Cannot defend a release; a prompt or corpus change has no regression signal | `evaluation-logbook.md` L-006; `requirements.yaml` NFR-001/002/003 | Sprint 3 (before the first RAG merge) | Member 2 | open | ADR-005, ADR-006, R-001, R-009 | 1 |
| DBT-002 | Evaluation debt | `scripts/validate_req.py`, `check_trace.py`, `check_permissions.py`, `check_manifest.py`, `check_ai_log.py`, `check_test_approval.py` (absent) | Every gate described in the docs is currently manual; drift is undetectable | Reviewers re-check by eye; a stale ID survives a sprint | `verification-constraints.md` §2, §5; `docs/code-governance/ai-use-log.yaml` gate rows | Sprint 2 (governance skeleton) | Member 5 | open | ADR-010, GOV-004, GOV-005 | 2 |
| DBT-003 | Guardrail debt | `test/` (absent) | 13 invariants, 31 requirements and 17 runtime policies have no executable test; all enforcement is prose | Safety claims are unproven; a regression has no alarm | `invariants.md` status `declared`; `trace-matrix.md` 0 tested rows; `runtime-policy-catalog.md` §5 | Sprint 3 (core flow) | Member 5 with Member 3 | open | INV-SCOPE-001..006, INV-AUTH-001, INV-LANG-001, INV-CEFR-001, INV-SEC-001..002, INV-PROG-001, INV-CITE-001, R-003, R-007 | 1 |
| DBT-004 | Guardrail debt | `.opencode/permissions.jsonc` (empty), hooks absent | The permission model has 45 declared rows and zero executing hooks; protected paths are protected by review only | An agent can write a gate module; the boundary is a promise | `permission-model.md` §1, §3; `structural-constraints.md` §9 | Sprint 2 (before the first code session) | Member 5 | open | ADR-010, GOV-005, R-015 | 1 |
| DBT-005 | Guardrail debt | `mcp-tool-manifest.md` tools, dispatcher (absent) | 24 tools are specified but none is callable or enforced; human-only tools are rejected only by convention | Role separation is procedural, not technical | `mcp-tool-manifest.md` §5; ADR-010 | Sprint 2 | Member 5 | open | ADR-010, GOV-005 | 2 |
| DBT-006 | Evaluation debt | `test/acceptance/`, `src/frontend/` (absent) | No browser journey test and no accessibility suite; accessibility is not yet an SSOT requirement but is a release-quality concern | Accessibility and the end-to-end demo are unverified | `verification-constraints.md` VS-16 | Sprint 4 | Member 4 | open | none (not SSOT-backed) | 3 |
| DBT-007 | Prompt rot | `prompts/prompt_v1.0.0.yaml` (absent) | `PROMPT_VERSION` and ADR-006 reference a prompt file that does not exist | A model-facing change has no version to diff or replay | `configuration-governance.md` key table; logbook L-008 | Sprint 2/3 (before the first live call) | Member 2 | open | ADR-006, GOV-002, R-003 | 2 |
| DBT-008 | Untouchable code | `src/backend/safety_boundary/scope_guard.py`, `src/backend/safety_boundary/citation_validator.py`, `src/backend/auth/security.py` (absent) | The three gate modules are human-only, but no human author is named and no review pair is assigned. Partial: `citation_validator.py` and `prompts/prompt_v1.0.0.yaml` have one of the two required reviewers (Member 1 PM read both against ADR-005/INV-CITE-001/NFR-QUAL-003; second reviewer Member 5 pending per `review-memo.md` MEMO-002 R-1); `scope_guard.py`/`auth/security.py` remain unassigned | The build blocks at the gate, or the gate is written by the agent it is meant to bound | `permission-model.md` §2; `structural-constraints.md` §8; `review-memo.md` MEMO-002 R-1 | Sprint 2 (assign authors) | Member 3 | open (1 of 2 reviewers on citation path; scope/auth paths open) | INV-SCOPE-001, INV-CITE-001, INV-AUTH-001, ADR-010 | 1 |
| DBT-009 | Human/cognitive debt | Project-wide | Corpus, retrieval, prompt and evaluation knowledge sits mainly with Member 2; no runbook or rotation is scheduled | A member absence stops the RAG workstream; review becomes single-person | `risk-list.md` R-011 | Sprint 2 (pairing) and Sprint 4 (rotation) | Member 1 | open | R-011 | 2 |
| DBT-010 | Hidden dependencies | Docs and planned tree | The docs reference scripts, directories and tests that do not exist yet (`planned:` evidence); an agent may treat them as present | False assumptions in a build session; wasted attempts | `trace-matrix.md` evidence legend; `verification-constraints.md` | Sprint 2 (create the skeleton) | Member 5 | open | R-015 | 3 |

## 3. Ranking

Ordered by **interest x blast radius**:

1. **DBT-001 / DBT-003 / DBT-004 / DBT-008** - high interest on the safety or release claim; blast radius is the whole system or the first build round.
2. **DBT-002 / DBT-005 / DBT-007 / DBT-009** - high or medium interest; blast radius is a workflow or a workstream.
3. **DBT-006 / DBT-010** - medium interest now, grows near release or after a misleading build session.

A row's rank changes when its trigger fires or its interest changes; age is not a ranking input.

## 4. Paid debt

None. A paid row moves here with `closed`, the commit that paid it and the date. Closing a row without a commit or a passing test is not allowed.

## 5. Done-when status

- [x] Every "planned/none yet" trace-matrix cell maps to DBT-002 or DBT-003.
- [x] Every guardrail-debt row names the invariant or rule that is currently prose-only.
- [ ] Rows that are paid are `closed` with the commit that paid them; none yet.
- [x] Every row has an owner, an interest statement, a trigger and a linked artifact.
