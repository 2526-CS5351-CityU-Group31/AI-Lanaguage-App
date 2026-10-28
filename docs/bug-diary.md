# Bug diary

**Purpose:** for each significant bug, record what happened, why, what fixed it, and **which invariant gap let it through**.
**Owner:** Member 5 (QA & Governance); the fixer writes the first draft.
**Rule from the revision-build section of the deck:** when a bug is an *architecture gap* rather than a code bug - the agent followed the spec and the spec was insufficient - the entry must say so, and it becomes the trigger for a delta specification (a new ADR or baseline), not a patch.

## 1. Index

| BUG | Date | Commit/build | Symptom (one line) | Classification | Invariant gap | Regression test |
|---|---|---|---|---|---|---|
| - | - | - | No bugs recorded at baseline; no runtime exists | - | - | - |

**Zero entries as of 2026-10-27.** This is not a claim that the design is defect-free; it records that nothing has executed. The first entry is required for any P0 finding in `review-memo.md` or any incident in `evaluation-logbook.md`.

## 2. Entry template

### BUG-NNN - <one-line title>

| Field | Value |
|---|---|
| BUG id | `BUG-NNN` |
| Date | `<YYYY-MM-DD>` |
| Commit / build | `<sha>` / `<run id>` |
| Symptom | Observable behaviour with the number that was wrong (e.g. "dashboard showed 7 words, events aggregated to 6") |
| Reproduction | Minimal command or fixture that reproduces deterministically |
| Classification | `spec` / `design` / `code` / `test` / `environment` / `model-behaviour` - pick one primary |
| Root cause | The mechanism, not the symptom ("the fallback swallowed the exception") |
| Fix | What changed, with file:line, and the ADR/invariant it aligned to |
| Invariant gap | Which `INV-*` should have caught it; if none exists, the new invariant id to add |
| Regression test | Test id that fails before and passes after; link to the CI run |
| Follow-up | `DBT-NNN`, or `none` with a reason |
| Status | `open` / `fixed` / `closed` with evidence date |

**Root-cause rule:** "it failed" is not a root cause. Name the mechanism: a missing guard, a swallowed exception, a default that allowed instead of denied, a test that could not fail, a prompt contract that omitted a field.

**Invariant-gap rule:** every entry names the gap. "None found - no invariant covers this" is acceptable and must create a new invariant row (append-only) before the fix is merged.

**Architecture-gap rule:** if the agent followed an ambiguous spec, the entry says "architecture gap" and opens a delta specification. It does not silently patch the code and leave the spec wrong.

## 3. What counts as significant

- Any P0 or P1 finding in a review memo.
- Any incident in the evaluation logbook.
- Any defect that escaped a test suite the project claims is a gate.
- Any defect whose fix changes a rule, threshold or interface rather than a line.

A typo in a comment is not a diary entry; it is a commit.

## 4. Done-when status

- [x] Zero P0 findings exist, so the "every P0 has an entry" rule is vacuously satisfied.
- [ ] Every future entry names an invariant gap; the template requires it.
- [ ] Every regression test is in a suite the CI gate runs (`DBT-002`, `DBT-003`).
- [ ] An architecture-gap entry triggers a delta specification, not a silent patch.
