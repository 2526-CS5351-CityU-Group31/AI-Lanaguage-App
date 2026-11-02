# Verification constraints - baseline R1

**Purpose:** state how evidence must be produced, which gate blocks what, and what a reviewer can reproduce from a fresh checkout.
**Consumers:** Verification agent (executes this table), CI, reviewers.
**Owner:** Member 5 (QA & Governance).
**Status:** declared. The commands below are the contract the future scripts/tests must satisfy. Gaps tracked by `DBT-001`-`DBT-006`.

## 1. The four verification rules

| Rule | Constraint | How checked | Failure |
|---|---|---|---|
| V1 - Fit-criterion coverage | Every requirement in `requirements.yaml` has >=1 test whose docstring names its ID; every fit criterion has a measurable assertion | `scripts/check_trace.py` + test docstring tags; trace-matrix row names the test | Requirement without a test blocks merge |
| V2 - Invariant coverage | Every invariant in `invariants.md` has a test that **fails when violated**, not a happy-path assertion | Negative/fault-injection test; must fail on pre-fix build; evidence in logbook | Missing or passing-on-broken-build test blocks release |
| V3 - Traceability | Every test references its requirement/invariant in its docstring or name | AST/grep docstring check; `test/structural/test_docstring_trace.py` | Untagged test is an orphan and fails Tier 1 |
| V4 - No regression across rounds | Every round runs all prior rounds' suites; exact commands listed; zero failures | Canonical command block run in order; prior suite cannot be skipped | Any failure blocks merge |

### Test docstring format

```python
def test_cross_user_session_denied():
    """INV-AUTH-001: a foreign session id returns 404 with no body and no mutation."""
```

A test may name more than one ID, but at least one must resolve. A test with no tag is not evidence.

## 2. Canonical gate commands

These commands are **byte-identical** to blueprint §8. Copy-paste them; do not retype them in a second style.

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
npm --prefix src/frontend run test:a11y
python scripts/check_ai_log.py --pr $PR
```

## 3. Three tiers and gating order

| Tier | Name | Commands | Runs when | On failure | Blocks |
|---|---|---|---|---|---|
| 1 | Structural | validate_req, check_trace, check_permissions, check_manifest, `pytest test/structural` | Every push and PR | Stop; fix structure; no Tier 2 | Any merge |
| 2 | Correctness/regression | `mypy --strict src`, `pytest test/offline` | After Tier 1 | Stop; fix or revert | Any merge |
| 3 | Behavioral | offline replay, live replay, accessibility | After Tier 2; live only with approval | Invariant failure blocks; quality miss -> human review | Release and model-facing merge |

- No parallelism across tiers. A skipped Tier 3 is a failed Tier 3 for a release-bound change. "The provider was unavailable" is not a pass; the change waits.
- The offline suite must run without paid API access. Stub adapters are required for the model and retrieval ports.
- Live evaluation runs with capped credentials, approved by the release owner, results linked in the PR.

## 4. Release thresholds (single source: `requirements.yaml`)

| Metric | Threshold | Verification | Requirement | Fallback |
|---|---|---|---|---|
| Citation validity | 100% | `test/offline/test_safety_boundary/test_citation_validator.py::test_zero_hallucinated_citations` | NFR-QUAL-003 | Block release; quarantine failing case |
| Retrieval recall@5 | >= 0.85 | `test/offline/test_ai_companion/test_retrieval_eval.py::test_recall_at_5` | NFR-QUAL-001 | REVIEW; tune retrieval; block release |
| Grounded correctness | >= 0.80 | `test/live/test_semantic_eval.py::test_grounded_correctness` | NFR-QUAL-002 | REVIEW; revise prompt/corpus; block release |
| Policy escapes | 0 | `test/offline/test_safety_boundary/test_prompt_injection.py::test_zero_policy_escapes` | NFR-SEC-001 | Block release; security review |
| Cross-user exposure | 0 | `test/offline/test_auth/test_authorization.py::test_cross_user_isolation` | INV-AUTH-001 | Block release; incident |
| Turn p95 latency | <= 12.0 s | `test/live/test_latency.py::test_p95_response_latency` | NFR-PERF-001 | REVIEW; block release |
| Prompt tokens/turn | <= 1,500 | `test/offline/test_ai_companion/test_token_budget.py::test_token_cap_enforcement` | NFR-COST-001 | REVIEW; reduce context |
| Off-topic refusal | 100% | `test/offline/test_safety_boundary/test_scope_guard.py::test_off_topic_refusal_accuracy` | NFR-QUAL-004 | Block release |
| CI blocking gates | all 6 pass | workflow run | NFR-GOV-001 | Block merge |
| AI-log gate | exit 0 | workflow run | NFR-GOV-002 | Block merge |

A threshold change is a requirements change and a logbook row; never edit only here. The values above must match `requirements.yaml` exactly - same value, same unit, no rounding drift.

## 5. Verification specification table

| # | Constraint | What is verified | Method | Pass condition | Tier | Blocks |
|---|---|---|---|---|---|---|
| VS-01 | Registry | Schema, unique IDs, required fields | `validate_req.py` + JSON Schema | Exit 0; 31 requirements; 0 schema errors | 1 | merge |
| VS-02 | Trace coverage | One row per requirement; no dead rows | `check_trace.py` | 31/31; 0 orphans | 1 | merge |
| VS-03 | Module map | 18 modules, one per element; names match | `pytest test/structural/test_module_map.py` | 18/18; 0 duplicates | 1 | merge |
| VS-04 | Import boundaries | C1-C7 contracts | import-linter + AST | 0 violations | 1 | merge |
| VS-05 | Config boundary | No `os.environ` outside config | grep + AST | no output | 1 | merge |
| VS-06 | Single writer | Each store has one writer | AST + grants | 0 second writers | 1 | merge |
| VS-07 | Permissions | Table vs `permissions.jsonc` | `check_permissions.py` | 0 drift | 1 | merge |
| VS-08 | Manifest | Every tool has ADR + invariant + one caller | `check_manifest.py` | 0 unowned tools | 1 | merge |
| VS-09 | Invariants | 13 invariants have failing tests | `pytest test/offline` | 13/13 pass; each fails on a deliberate break | 2 | merge/release |
| VS-10 | Fit criteria | Each Must requirement has a test | Test tags + trace matrix | 30/30 Must covered | 2 | merge |
| VS-11 | Type safety | Strict typing of `src/` | `mypy --strict src` | 0 errors | 2 | merge |
| VS-12 | Offline regression | Deterministic suite, no network | `pytest test/offline` | 0 failures, 0 safety skips | 2 | merge |
| VS-13 | Grounding quality | Recall, citation validity, correctness | Offline replay + human scoring | thresholds in §4 | 3 | release |
| VS-14 | Adversarial safety | Injection, identity, malformed output | EVAL-1.0.0 adversarial | 0 escapes, 0 exposures | 3 | release |
| VS-15 | Live behaviour | Same metrics against real provider | Live replay, approved credentials | thresholds in §4; fail closed if it cannot run | 3 | release |
| VS-16 | Accessibility | Five flows | axe-core + keyboard script | 0 critical | 3 | release |
| VS-17 | AI log | Code/prompt diff has a session entry | `check_ai_log.py --pr` | 0 gaps | pre-merge | merge |
| VS-18 | Test approval | Approval artifact predates implementation | `check_test_approval.py --pr` | 0 unapproved commits | pre-merge | merge |
| VS-19 | Frozen paths | Zero diff on frozen artifacts | `git diff --exit-code` | 0 changed lines | pre-merge | merge |
| VS-20 | Scope | No out-of-scope routes | `test/structural/test_scope.py` | 0 routes | 1 | merge |

## 6. Test locations and structure

| Suite | Location | Network? | Purpose | Naming |
|---|---|---|---|---|
| Structural | `test/structural/` | no | Imports, module map, docstrings, config, scope | `test_<rule>.py` |
| Offline | `test/offline/` | no | Domain rules, invariants, scope, auth, vocabulary, progress | `test_<area>.py`; invariants under `test/offline/.../test_inv_<id>.py` |
| Live | `test/live/` | yes, approved | Provider quality, latency, live replay | `test_live_<area>.py`; skipped by default |

- Offline tests use stub `ModelGateway` and `RetrievalService` adapters; no test may call a provider.
- Live tests require `LLM_MODE=live`, credentials, and a human approval; they fail closed if the environment is missing.
- Test fixtures are independent of the code under test; a fixture that imports the implementation under test is a review finding.
- A skipped safety test is reported as a failure in the release gate, not as a pass.

## 7. Test approval before implementation

The approval artifact contains:

| Field | Rule |
|---|---|
| Requirement IDs | At least one resolvable `FR-`/`INV-`/`NFR-` |
| Proposed tests | Test names and the fit criterion each covers |
| Plan revision | The commit or plan id the approval applies to |
| Approver | Named human, not the author |
| Approved at | ISO timestamp before the first implementation commit |
| Rollback | The step that returns to the last green state |

A materially changed plan requires a new approval; appending implementation detail inside the approved scope does not.

## 8. Pre-submission checklist

Run in order from a fresh clone; record the command and result in the PR or report.

1. `python scripts/validate_req.py docs/req/requirements.yaml` -> exit 0, 31 requirements, 0 schema errors.
2. `python scripts/check_trace.py` -> 31 rows, 0 orphan requirements, 0 dead rows.
3. `python scripts/check_permissions.py` -> 0 differences between the table and `permissions.jsonc`.
4. `python scripts/check_manifest.py` -> every tool has one ADR, one invariant, one caller; 0 violations.
5. `pytest test/structural -q` -> pass; 0 module-map, import, docstring, config or scope violations.
6. `mypy --strict src` -> 0 errors.
7. `pytest test/offline -q` -> pass; 0 skipped safety tests.
8. `python scripts/run_eval.py --suite evals/EVAL-1.0.0.yaml --offline` -> thresholds in §4.
9. `python scripts/run_eval.py --suite evals/EVAL-1.0.0.yaml --live` -> thresholds in §4; evidence linked; fails closed if credentials are missing.
10. `npm --prefix src/frontend run test:a11y` -> 0 critical violations on five flows.
11. `grep -rn "os\.environ\|os\.getenv\|load_dotenv" src --include='*.py' | grep -v 'config.py:'` -> no output.
12. `git diff --exit-code -- docs/req/requirements.yaml docs/architecture/adr architecture-blueprint.md prompts/ evals/` -> no diff against the frozen baseline (except in a declared delta round).
13. `python scripts/check_ai_log.py --pr $PR` -> 0 code/prompt diffs without a session entry.
14. `python scripts/check_test_approval.py --pr $PR` -> 0 implementation commits without a prior approval.

## 9. Evidence rules

- Every metric is reported with `n`, the eval version, the corpus/prompt/model versions and the date. A bare "100%" is not evidence.
- Human scoring uses two reviewers and a 0-2 rubric per criterion; disagreements are adjudicated and the adjudication is recorded.
- A failing test is kept in the logbook with the build id before the fix; deleting the failure evidence is a process defect.
- CI artifacts are retained for 90 days; the evaluation logbook is permanent.
- A green local run is not a gate; only the CI run on the PR is.

## 10. Done-when status

- [x] The canonical commands are defined once and copied byte-identically into blueprint §8.
- [x] Every `INV-*` has a named failing-test mapping (V2), even though the test does not exist yet.
- [x] Tier thresholds match `requirements.yaml` exactly (same value, unit and sample).
- [ ] The checklist reproduces on a fresh clone (`DBT-001`, `DBT-003`).
- [ ] Every invariant test fails on the pre-fix build and the evidence is in the logbook (`DBT-003`).
- [ ] Live replay is wired with capped credentials and a fail-closed behaviour (`DBT-001`).
