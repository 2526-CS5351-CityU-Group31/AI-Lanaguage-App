# Review memos

**Purpose:** for each PR, record whether it is aligned with the specification and architecture, whether code and test quality are acceptable, and the verdict.
**Owner:** Member 5 (QA & Governance); every reviewer writes their own memo section.
**Rule:** the memo reviews **governance**, not every line. A P0 finding must cite the invariant or ADR it violates; a P0 without a citation is a style opinion and must be downgraded to P2.

**Verdict vocabulary:** `APPROVE` / `CHANGES REQUIRED` / `REJECT`. No other value is valid.

## 1. Index

| PR | Title | Commit range | Author | Reviewer | Date | Verdict |
|---|---|---|---|---|---|---|
| - | No implementation PR exists as of 2026-10-27 | - | - | - | - | - |

There are **zero** merged code or prompt PRs at baseline. The baseline documentation is not a PR and is not reviewed here; the first memo will cover PR-001, the first implementation change.

## 2. Memo template (copy per PR, newest first)

### MEMO-NNN - PR-<ID>: <title>

| Field | Value |
|---|---|
| PR id, title | `<id>` - `<title>` |
| Commit range | `<abc123>..<def456>` |
| Author / reviewer | `<author>` / `<reviewer>` |
| Date | `<YYYY-MM-DD>` |
| Linked requirements | `REQ-LANG-...` |
| Linked ADR / invariants | `ADR-NNN` / `INV-NNN` |
| Plan approval | `<artifact id, approver, timestamp>` |
| AI use log | `S-NNN` |
| CI run | `<run id / link>` |
| Verdict | `APPROVE` / `CHANGES REQUIRED` / `REJECT` |

**Spec alignment**

- Which `REQ-*` does this change serve? List them; a requirement touched but not cited is a finding.
- Does the change alter a fit criterion or threshold? If yes, where is the delta block?
- Are any requirements marked `implemented`/`verified` without evidence?

**Architecture alignment**

- Which ADR section and invariant apply? Cite them.
- Does the change respect the authority boundary (no model write path, no gate bypass)?
- Does it add a module, dependency or cross-boundary import? If yes, was the ADR and module table updated first?
- Does it change a frozen path? If yes, is the approval and ADR present?

**Code quality**

- One element per module; names match the module table.
- Duplication, dead branches, error handling, naming, docstring traceability (`ADR-...`, `INV-...`).
- Typed boundaries; no `Any` leaking across a service boundary; no raw SQL in a service.

**Test quality**

- New tests map to fit criteria; negative test present for every new invariant claim.
- Determinism: offline vs live; no network in `test/offline/`.
- Does the test fail on the pre-fix build? Evidence link.
- Is a safety test skipped? A skip is a P1.

**Security**

- Input sanitisation, authorization on every record, secrets, dependency injection, log redaction.
- Any new prompt surface or retrieved-content path? Re-run the adversarial set.
- Any cross-user path? Run the 20-probe suite.

**Efficiency**

- Token/cost impact, unnecessary model calls, retrieval count, latency change.
- Does the change affect the 8k context budget or the US$0.04 session target?

**Operational metadata**

- Model version, prompt version, corpus version, config keys, log events added.
- Are the new fields in the observability schema, and redacted?

**Findings**

| ID | Severity (`P0`/`P1`/`P2`) | File:line | Finding | Cited invariant/ADR | Resolution |
|---|---|---|---|---|---|
| F-01 | P1 | `src/foo.py:42` | ... | `INV-001`, ADR-005 §Decision | fixed in `<commit>` / `DBT-NNN` |

- **P0** blocks the merge: an invariant or authority violation, a secret, a cross-user path, a gate bypass.
- **P1** must be fixed before merge or moved to `debt-register.md` with an owner and trigger.
- **P2** is a follow-up; it may merge but must be recorded.

**Verdict rationale**

One paragraph: why this verdict, which findings drove it, and what would change it. The verdict must be one of the three exact strings.

## 3. Review rules

1. **Independence:** the author may not review their own PR, and the Build agent may not write the Verify memo.
2. **Evidence over assertion:** "tests pass" is not a review finding; the CI run id and the command are.
3. **P0 citation:** a P0 must name the invariant or ADR it violates. If it cannot, downgrade it.
4. **Frozen paths:** a change to `docs/req/requirements.yaml`, an accepted ADR, the blueprint, CI, prompts or permissions requires a human author and an ADR; the memo must record the approval id.
5. **AI log:** a code or prompt PR without a new `docs/ai-use-log.yaml` session is a P0 for the process, not a P2.
6. **Resolution:** every P0/P1 is either fixed in the PR or moved to `debt-register.md` with a `DBT-*` id before merge. An open P0 is never merged.
7. **Retrospective:** if a defect escapes, the review memo is updated with the missed finding and a link to the bug diary entry.

## 4. Done-when status

- [x] The template contains every required section, including spec, architecture, code, test, security, efficiency, operational metadata, findings and verdict.
- [x] Verdict values are restricted to the three allowed strings.
- [x] P0 findings must cite an invariant or ADR.
- [ ] Every merged PR has a memo (`DBT-002`; no PRs yet).
- [ ] Every P0/P1 has a resolution or a debt row (`DBT-002`).
