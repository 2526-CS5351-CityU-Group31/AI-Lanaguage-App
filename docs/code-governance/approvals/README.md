# Test-approval artifacts

**Owner:** the approving human (never the implementing agent).
**Enforced by:** `scripts/check_test_approval.py` in Gate 1 of `.github/workflows/ci.yml`.
**Contract:** `docs/code-governance/ci-gates-design.md` §A.1; `verification-constraints.md` §7 and VS-18.

Gate 1 proves one thing: the plan and its tests were approved **before** implementation
code was written. The evidence is this file, committed to the PR branch before any commit
that touches `src/`, `prompts/` or `migrations/`.

## Who writes it, and when

1. The PR author posts the plan and the proposed tests.
2. A named human other than the author reviews them and commits the artifact:
   `docs/code-governance/approvals/PR-<number>.yaml`, where `<number>` is the PR number.
3. Only then does implementation start.

A materially changed plan needs a new artifact. Appending implementation detail inside the
already-approved scope does not.

## Format

One file per PR, named `PR-<number>.yaml`:

```yaml
pr: 7
approver: "Adrian"                     # a named human, not the author
approved_at: "2026-11-15T10:00:00Z"    # ISO 8601; must precede the first implementation commit
requirement_ids: ["NFR-GOV-001"]      # each id must exist in docs/req/requirements.yaml
tests:
  - name: "test/offline/test_safety_boundary/test_citation_validator.py::test_reject_invalid_citations"
    covers: "INV-CITE-001"
rollback: "Revert the branch."        # the step back to the last green state
```

Required fields: `approver`, `approved_at`, `requirement_ids` (non-empty), `tests`
(non-empty; a string or a `{name, covers}` mapping), `rollback`. `pr` is optional but
must equal the PR number when present.

Proposed tests are approved *before* they exist, so Gate 1 does not check that the named
tests are already in the tree.

## What makes Gate 1 fail

| Code | Meaning |
|---|---|
| `APPROVAL_MISSING` | no `PR-<number>.yaml` for this PR |
| `APPROVAL_MALFORMED` | unparsable, or a required field is missing/empty/wrong type |
| `SELF_APPROVAL` | the approver authored an implementation commit (matched on name, email or email local part) |
| `APPROVAL_AFTER_IMPLEMENTATION` | `approved_at` is later than the first implementation commit |
| `REQUIREMENT_UNKNOWN` | a `requirement_ids` entry is not in `docs/req/requirements.yaml` |
| `BASE_REF_MISSING` | the base ref cannot be resolved (fetch the base branch with `fetch-depth: 0`) |

The gate has no grandfathering and no identity map: it applies to every PR from the commit
that switched it on, and it judges the artifact's declared `approved_at` time, not the time
the artifact was committed.

## Local check

```bash
python scripts/check_test_approval.py --pr <number> --base origin/main
```

Exit 0 prints a one-line summary; exit 1 prints exactly one of the codes above on stderr.
