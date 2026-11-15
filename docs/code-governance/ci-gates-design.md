# CI gates Gate 1 (test approval) and Gate 4 (semantic evaluation) — implementation design

**Status:** implemented 2026-11-15. Gate 1 blocks PRs; Gate 4 blocks PRs on the offline
tier and runs the live tier on tag pushes and manual dispatch. `.github/workflows/ci.yml`
is a human-only path (`structural-constraints.md` §2), so the wiring below needs human
review before merge. Decision owner: Member 1 (Adrian, PM & governance).
**Implements:** ADR-010 G1/G2; `verification-constraints.md` VS-18, §3–§4, §7.
**Audience:** Member 5 (Luming) implements the two scripts, the eval file, and the CI wiring below.
**Debt:** pays down `DBT-002` (and the Gate-1 half of `DBT-003`).

This is deliberately minimal. Keep the implementation simple; do not add
grandfathering back-references, identity maps, or base-ref anti-gaming checks.

---

## Part A — Gate 1: Test approval

**Idea:** a human approves the plan and tests *before* implementation code is
written. The gate proves the order. It only runs on PRs from the moment it is
switched on, so earlier merged work is untouched by construction.

### A.1 Approval artifact

**File:** `docs/code-governance/approvals/PR-<number>.yaml` (one per PR). A
human writes and commits it before coding.

```yaml
pr: 7
approver: "Adrian"
approved_at: "2026-11-15T10:00:00Z"   # ISO 8601
requirement_ids: ["NFR-GOV-001"]
tests:
  - name: "test/offline/test_safety_boundary/test_citation_validator.py::test_reject_invalid_citations"
    covers: "INV-CITE-001"
rollback: "Revert the branch."
```

Required: `approver`, `approved_at`, `requirement_ids` (each a `FR`/`NFR`/`INV`
id that exists in `docs/req/requirements.yaml`), `tests` (non-empty), `rollback`.

### A.2 `scripts/check_test_approval.py`

CLI: `python scripts/check_test_approval.py --pr <number> [--base origin/main]`

Checks:
1. Artifact `approvals/PR-<n>.yaml` exists and parses. Else `APPROVAL_MISSING`.
2. `approver` is not the author of any implementation commit. Else `SELF_APPROVAL`.
3. `approved_at` is `<=` the first implementation commit time
   (`git log --format=%cI <base>..HEAD -- src prompts migrations`). Else
   `APPROVAL_AFTER_IMPLEMENTATION`.
4. Every `requirement_ids` entry exists in `requirements.yaml`. Else
   `REQUIREMENT_UNKNOWN`.

Exit 0 with a one-line summary; non-zero with the typed code on failure.

### A.3 CI wiring

Replace the Gate 1 placeholder in `.github/workflows/ci.yml` (~lines 15-25):
`if: github.event_name == 'pull_request'`, run the script with
`--pr ${{ github.event.pull_request.number }}`, blocking.

Flip to blocking only after the script and its test exist and pass.

### A.4 Test

`test/offline/test_scripts/test_check_test_approval.py` (temp git repos): valid →
exit 0; missing artifact → `APPROVAL_MISSING`; approver == author →
`SELF_APPROVAL`; approval after first impl commit →
`APPROVAL_AFTER_IMPLEMENTATION`; unknown requirement → `REQUIREMENT_UNKNOWN`.

---

## Part B — Gate 4: Semantic evaluation

**Idea:** check the release thresholds; run the stubbed (offline) part on every
PR, the real (live) part only at release. Unfinished metrics are reported as
pending, never block a PR.

### B.1 Tiers

| Tier | Runs on | Blocking | Credentials |
|---|---|---|---|
| offline | every PR | yes | none (stubbed) |
| live | release / manual dispatch | yes at release | capped key + approval |

On a PR, the live tier **skips with a recorded exception**; at release it
**fails closed**. This note is the authority for that split.

### B.2 `evals/EVAL-1.0.0.yaml`

`evals/` is not frozen (`structural-constraints.md` §2) — creating this file is
allowed.

```yaml
suite: EVAL-1.0.0
version: "1.0.0"
cases:
  - id: <slug>
    tier: offline | live
    requirement: <FR|NFR|INV id>
    threshold: <number>
    comparator: eq | gte | lte | zero
    test: <pytest node id>
    status: active | pending     # pending = reported, never blocks a PR
```

Seed all eight cases; `active` = has a passing offline test today, everything
else `pending`:

| id | tier | requirement | threshold | comparator | status |
|---|---|---|---|---|---|
| citation-validity | offline | NFR-QUAL-003 | 1.00 | eq | active |
| prompt-tokens | offline | NFR-COST-001 | 1500 | lte | active |
| retrieval-recall | live | NFR-QUAL-001 | 0.85 | gte | pending |
| grounded-correctness | live | NFR-QUAL-002 | 0.80 | gte | pending |
| policy-escapes | offline | NFR-SEC-001 | 0 | zero | pending |
| cross-user-exposure | offline | INV-AUTH-001 | 0 | zero | pending |
| turn-p95-latency | live | NFR-PERF-001 | 12.0 | lte | pending |
| off-topic-refusal | offline | NFR-QUAL-004 | 1.00 | eq | pending |

Threshold values must match `requirements.yaml`; mismatch → `THRESHOLD_DRIFT`.

### B.3 `scripts/run_eval.py`

CLI: `python scripts/run_eval.py --suite evals/EVAL-1.0.0.yaml --offline|--live`

- Load suite, validate schema, assert thresholds vs `requirements.yaml`.
- `--offline`: run `tier: offline` + `status: active` cases; `pending` →
  `SKIPPED_PENDING`. Exit non-zero if an active case misses.
- `--live`: require `LLM_MODE=live` + credentials; missing → fail closed, or
  `SKIP_LIVE_NO_ENV` (exit 0) only when `--allow-skip` is passed (PR context).
- Write evidence to `reports/eval/`.

### B.4 CI wiring

Replace the Gate 4 placeholder (~lines 73-82):
- offline job: `if: github.event_name == 'pull_request'`, `--offline`, blocking.
- live job: `if: workflow_dispatch || refs/tags/*`, `--live` (no `--allow-skip`),
  blocking at release.

Flip to blocking only after `run_eval.py` + `EVAL-1.0.0.yaml` + tests exist.

### B.5 Test

`test/offline/test_scripts/test_run_eval.py`: active offline pass → 0; active
offline fail → 1; `pending` reported not failed; threshold mismatch →
`THRESHOLD_DRIFT`; `--offline` never runs live cases.

---

## Sequencing

1. Gate 1 script + artifact schema + test.
2. Gate 4 `run_eval.py` + `EVAL-1.0.0.yaml` + test.
3. Wire both in `ci.yml` (co-owned by Member 1 + 5 → both review).
4. Flip to blocking once each script's test passes.
5. Add SES entries; update `DBT-002`, `DBT-003`, `evaluation-logbook.md` L-006.

---

## Implementation notes (2026-11-15)

What the shipped code adds beyond this note, and the one conflict that needs a decision.

1. **Two extra typed codes on Gate 1.** `BASE_REF_MISSING` and `GIT_UNAVAILABLE` join the
   four named codes, and `APPROVAL_MALFORMED` carries the field-level rejections (missing
   `rollback`, empty `tests`, a non-ISO `approved_at`, a `pr` that disagrees with `--pr`,
   a legacy `REQ-LANG-*` id). Without it, a malformed artifact would either pass or be
   reported as `APPROVAL_MISSING`, which would hide the real defect. Every extra code
   fails closed.

2. **Gate 1 compares `approved_at`, not the artifact's commit time.** A retroactive
   artifact that declares an earlier timestamp passes; a commit that lands after the first
   implementation commit does not fail by itself. That follows §A.2 check 3 as written and
   is covered by `test_declared_approval_time_decides_not_commit_order`.

3. **`run_eval.py` takes three extra flags for hermetic tests:** `--root`,
   `--requirements`, `--report-dir`. The canonical commands in `verification-constraints.md`
   §2 are unchanged and stay valid; the flags only let the offline tests build a throwaway
   checkout instead of mutating the repository's suite.

4. **A live run with no active live case fails closed.** `LIVE_NO_ACTIVE_CASES` mirrors
   `verification-constraints.md` §3 ("a skipped Tier 3 is a failed Tier 3"): with the three
   live cases still `pending`, Gate 4 cannot pass at release yet. That is the honest state
   of `DBT-001`, not a bug; it clears when a live case flips to `active`.

5. **Conflict to resolve: is `evals/` frozen?** `structural-constraints.md` §2 does not list
   `evals/`, and §B.2 of this note states it is not frozen, but
   `verification-constraints.md` §8 item 12 includes `evals/` in the
   `git diff --exit-code` frozen-path command. The two cannot both hold. The suite is
   versioned (`EVAL-1.0.0`); adding `EVAL-1.1.0` should not require touching `EVAL-1.0.0`.
   Recommendation: keep `evals/` out of the frozen list and freeze the *published suite
   version*, per ADR-001's "published content versions are immutable" rule. Decision owner:
   Member 1.

