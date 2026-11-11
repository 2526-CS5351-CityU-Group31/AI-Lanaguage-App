# Review memos

**Purpose:** for each PR, record whether it is aligned with the specification and architecture, whether code and test quality are acceptable, and the verdict.
**Owner (template):** Member 5 (QA & Governance).
**Author of each memo:** the **reviewer of that PR, never its author.** The default reviewer is the PM (Member 1); Member 5 reviews any PR the PM authors. A reviewer may not write the memo for their own change.
**Rule:** the memo reviews **governance**, not every line. A P0 finding must cite the invariant or ADR it violates; a P0 without a citation is a style opinion and must be downgraded to P2.

**Verdict vocabulary:** `APPROVE` / `CHANGES REQUIRED` / `REJECT`. No other value is valid.

## 0. Who reviews whom

| PR author | Reviewer (writes the memo) |
|---|---|
| A teammate (Member 2/3/4) | PM (Member 1) |
| PM (Member 1) | Member 5 |
| Member 5 | PM (Member 1) |

Each PR has exactly **one** reviewer and **one** memo section. The author fills the PR description (requirements, files, tests); the reviewer fills the memo (findings, verdict). Independence is mandatory: author ≠ reviewer. If neither the PM nor Member 5 is available, the PR waits rather than self-approving.

## 1. Index

| PR | Title | Commit range | Author | Reviewer | Date | Verdict |
|---|---|---|---|---|---|---|
| PR-4 | AI companion foundation (contracts, retrieval, prompt, tutor, proposal-only RagPipeline) | `1fff55d..97faaec` | Member 2 (Leon) | Member 1 (Adrian) / PM | 2026-11-11 | APPROVE |
| - | No implementation PR exists as of 2026-10-27 | - | - | - | - | - |

There are **zero** merged code or prompt PRs at baseline. The baseline documentation is not a PR and is not reviewed here; the first memo will cover PR-001, the first implementation change.

## 2. Memo template (copy per PR, newest first)

### MEMO-001 - PR-4: AI companion foundation (contracts, retrieval, prompt, tutor, proposal-only RagPipeline)

| Field | Value |
|---|---|
| PR id, title | 4 - AI companion foundation |
| Commit range | `1fff55d..97faaec` (commits `cf9abb0`, `336a184`, `1b7249d`, `d02fdc9`, `97faaec`) |
| Author / reviewer | Member 2 (Leon) / Member 1 (Adrian), PM |
| Date | 2026-11-11 |
| Linked requirements | `FR-CHAT-001`, `FR-RAG-001`, `INV-SCOPE-006`, `INV-CITE-001` (partial), `NFR-COST-001`, `NFR-SEC-001` (structural), `NFR-PERF-001` (partial), `NFR-GOV-002` |
| Linked ADR / invariants | ADR-001, ADR-005, ADR-006, ADR-007; INV-SCOPE-006, INV-CITE-001 |
| Plan approval | Approved in-session per `ai-use-log.yaml` SES-023..SES-025 (human-approved plan; tests-first; commit split) |
| AI use log | SES-023, SES-024, SES-025 |
| CI run | CI green on Leon's latest commit (`97faaec`) per branch author. Reviewer independently reproduced locally: `pytest test/offline -q` -> 54 passed; `mypy --strict src` -> Success (8 files); `check_ai_log.py --pr 4` -> exit 0. |
| Verdict | APPROVE |

**Reviewer note.** This memo addresses the six confirmations requested by the AI Foundation author. Each was checked against source and reproduced with the installed offline suite (pytest 54 passed, mypy --strict clean). All six are confirmed (five clean, #5 confirmed with a recorded deferral caveat). The only finding is a P2 test-consistency nit (F-01) plus three P2 follow-ups; none block the foundation contract.

#### Requested confirmations

| # | Claim | Verdict | Evidence |
|---|---|---|---|
| 1 | AI foundation is advisor-only, no write path | **CONFIRMED** | `ai_companion/**` imports only `{__future__, dataclasses, difflib, enum, math, re, typing, unicodedata}` plus `backend.ai_companion.*` and `backend.contracts.ai_companion`. No `database`, `auth`, `api`, `user_progress`, `vocabulary` or write-service import. No `open`/`environ`/`getenv`/file or network IO. Satisfies S4 C3/C5 and the blueprint §3.3 advisory-zone rule. Test: `test_ai_foundation_boundaries.py::test_ai_foundation_imports_are_bounded`, `::test_ai_foundation_has_no_environment_or_file_io`, `::test_no_network_calls_during_pipeline`. |
| 2 | `RagPipeline` returns no unvalidated model text | **CONFIRMED** | `RagPipeline.handle` sets `text=None` on every non-`accepted` path (`abstained`, `rejected`, `validator_error`). Only the `accepted` branch returns `verdict.validated_text` (falling back to `tutor_result.text` *after* an accepted verdict). Reproduced directly: a rejected verdict with sentinel text `UNVALIDATED_SECRET_MODEL_TEXT` returned `status=rejected, text=None`, no leak. Tests: `test_rag.py::test_validation_rejection_discards_model_text`, `::test_validator_exception_fails_closed`. |
| 3 | Zero retrieval calls for ungrounded turns | **CONFIRMED** | `RetrievalAdapter.retrieve` returns an empty `EvidenceSet` before validating or calling the service when `requires_grounding` is false; `RagPipeline` only calls `retrieve` when `request.requires_grounding` is true. Tests: `test_retrieval_conditions.py::test_conditional_retrieval_routing`, `::test_ungrounded_retrieval_returns_empty_even_with_candidates`, `test_rag.py::test_ungrounded_turn_skips_retrieval` (asserts `retrieval.calls == []`). Covers `INV-SCOPE-006` for the AI-companion slice. |
| 4 | Assembled prompts <= 1,500 tokens | **CONFIRMED** | `AssemblyConfig.layer_budgets.total` must equal `token_budget` (1500) at construction; the assemble loop cuts history, then marker, then evidence, then optional layers until `<= budget`, and fails closed with `BUDGET_UNSATISFIABLE` otherwise. Reproduced over 200 randomized adversarial inputs: max assembled = 792 tokens, all `<= 1500`. Tests: `test_token_budget.py::test_token_cap_enforcement`, `::test_default_layer_budgets_sum_to_1500`, `test_rag.py::test_prompt_budget_enforced_through_pipeline`. Token count is a deterministic `ceil(len/4)` estimate, not a provider tokenizer (see F-03). |
| 5 | Deferred safety-boundary/provider/DB work is acceptable | **CONFIRMED WITH FOLLOW-UP** | PR diff touches only `src/backend/ai_companion/**`, `src/backend/contracts/**`, `test/offline/test_ai_companion/**`, and `ai-use-log.yaml`; zero changes to `safety_boundary/`, `api/`, `auth/`, `database/`, `main.py`, `migrations/`, `prompts/`, `content/`, CI. The real `CitationValidator`, DB retrieval, and live provider are absent and referenced only as injected ports (`ResponseValidator`, `RetrievalService`, `ModelGateway`). Deferral is architecturally legitimate (advisory zone depends on authoritative gate via injection) **but** the deliverable must not be presented as completing `INV-CITE-001`/`NFR-SEC-001`; trace status stays "partial/declared". See F-04. |
| 6 | AI-use log entries satisfy Gate 6 | **CONFIRMED** | `scripts/check_ai_log.py --pr 4` -> `passed; 25 valid sessions, unique IDs, append-only history intact` (exit 0). PR adds SES-023/024/025 for `src/` changes under `ai/companion-foundation`. Satisfies `NFR-GOV-002`. (Independently re-run; matches the author's manual check.) |

**Spec alignment**

- Serves `FR-CHAT-001` (partial), `FR-RAG-001` (partial), `INV-SCOPE-006`, `NFR-COST-001`, and structurally `NFR-SEC-001`. All are cited in module/test docstrings.
- No fit criterion or threshold is altered; no requirements file change.
- No requirement is marked `implemented`/`verified` without evidence; `INV-CITE-001` and `NFR-SEC-001` remain partial/structural only.

**Architecture alignment**

- Advisory zone only (`Tutor`, `PromptAssembler`, `RagPipeline`, `RetrievalAdapter`, `contracts`); the authoritative `CitationValidator` is injected, not implemented here, so the one-way advisory->authoritative boundary is preserved.
- No module, dependency or cross-boundary import added; no frozen path changed.
- Layer ordering and evidence delimiting follow ADR-006; retrieved text is wrapped in `<<<UNTRUSTED_EVIDENCE>>>` delimiters and delimiter-spoofing is escaped. This is structural support for `NFR-SEC-001`, not the injection gate itself.

**Code quality**

- One element per module; names match `structural-constraints.md` S1. Typed boundaries, no `Any` leaking across services, no raw SQL. Docstrings carry `ADR-`/`INV-`/`FR-`/`NFR-` tags.
- Deterministic and fail-closed on retrieval/tutor/validator errors.

**Test quality**

- 54 offline tests; positive + negative coverage (invalid queries, rejection, validator exception, retry exhaustion, non-retryable error, budget overflow). No network; fake adapters record calls.
- Coverage gap: `test_ai_foundation_boundaries.py` `FOUNDATION_FILES` omits `prompt_assembly.py` (see F-01).

**Security**

- No secrets, no env reads, no file/network IO in the foundation. No cross-user path introduced. Retrieved-content path is delimited as untrusted data; adversarial replay is deferred with the safety boundary (F-04).

**Efficiency**

- Token cap enforced; retrieval is conditional so ungrounded turns pay zero retrieval cost. The 8k/US$0.04 wording in the template is legacy — the operative cap here is `NFR-COST-001` at 1,500 tokens (F-02 note).

**Operational metadata**

- Config keys: `CONTEXT_TOKEN_BUDGET=1500`, `compaction_message_limit=6`, layer caps summing to 1500; `TutorConfig` bounds (`max_attempts<=3`, `timeout_ms` 5–60s, `max_output_tokens`). Assembly metadata exposes per-layer tokens, dropped chunk/history counts, compaction flag, prompt version — usable for observability without new schema.

**Findings**

| ID | Severity | File:line | Finding | Cited invariant/ADR | Resolution |
|---|---|---|---|---|---|
| F-01 | P2 | `test/offline/test_ai_companion/test_ai_foundation_boundaries.py:19` | `FOUNDATION_FILES` omits `src/backend/ai_companion/prompt_assembly.py`, so the shared AST *env/file-IO* (S5) assertion does not cover it. Note: its import boundary (C3/C5) IS already covered by `test_prompt_assembly.py:216` (`test_module_has_no_provider_or_db_imports`) and network absence by `test_prompt_assembly.py:238`. The module complies today; only the consolidated env-IO guard omits it. | S5; ADR-001 advisory zone; `NFR-SEC-001` (structural) | Add `prompt_assembly.py` to `FOUNDATION_FILES` for consistency; no correctness risk. |
| F-02 | P2 | `docs/review-memo.md:80` | Template efficiency bullet still references the retired "8k context budget / US$0.04 session target", superseded by `NFR-COST-001` at 1,500 tokens. Reviewer ignored the stale wording; template should be updated. | `NFR-COST-001`, blueprint §8 | Update template wording in a docs-only follow-up. |
| F-03 | P2 | `src/backend/ai_companion/prompt_assembly.py:200` | Token accounting uses a deterministic `ceil(len/4)` heuristic, not a provider tokenizer. Correct for the offline gate but may under/over-count against the real provider; the 1,500 cap is only as accurate as the estimator. | `NFR-COST-001` | Document that live evaluation (`test/live`) must re-assert the cap with the provider tokenizer; track in debt register. |
| F-04 | P2 | `src/backend/ai_companion/rag_pipeline.py:84` | `INV-CITE-001`, `NFR-SEC-001` and `NFR-PERF-001` are only partial/structural here; the real `CitationValidator`, DB retrieval, and live latency/provider are deferred. Legitimate for this foundation, but the PR must not be recorded as verifying those invariants. | `INV-CITE-001`, `NFR-SEC-001`, `NFR-PERF-001` | Keep trace status partial; ensure safety-boundary + provider integration is a tracked next-branch deliverable. |

No P0 findings. No invariant/authority violation, no secret, no cross-user path, no gate bypass.

**Verdict rationale**

`APPROVE` — all six requested confirmations check out: #1-#4 and #6 clean, #5 confirmed with a deferral caveat (invariants stay partial, not verified). The single finding (F-01, now **P2**) is a test-consistency nit: `prompt_assembly.py` is left out of the shared `FOUNDATION_FILES` env/IO assertion, but its import boundary and network-absence are already covered by `test_prompt_assembly.py:216` and `:238`, and the module verifiably complies today. No P0 and no P1 remain. Governance posture is clean: lane-respecting diff, correct advisory boundary, fail-closed behaviour, and a passing Gate 6 log. F-01 and F-02..F-04 (P2) should be logged but do not block merge.

### MEMO-NNN - PR-<ID>: <title>

| Field | Value |
|---|---|
| PR id, title | `<id>` - `<title>` |
| Commit range | `<abc123>..<def456>` |
| Author / reviewer | `<author>` / `<reviewer>` |
| Date | `<YYYY-MM-DD>` |
| Linked requirements | `INV-` / `FR-` / `NFR-...` |
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
| F-01 | P1 | `src/foo.py:42` | ... | `INV-CITE-001`, ADR-005 §Decision | fixed in `<commit>` / `DBT-NNN` |

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
5. **AI log:** a code or prompt PR without a new `docs/code-governance/ai-use-log.yaml` session is a P0 for the process, not a P2.
6. **Resolution:** every P0/P1 is either fixed in the PR or moved to `debt-register.md` with a `DBT-*` id before merge. An open P0 is never merged.
7. **Retrospective:** if a defect escapes, the review memo is updated with the missed finding and a link to the bug diary entry.

## 4. Done-when status

- [x] The template contains every required section, including spec, architecture, code, test, security, efficiency, operational metadata, findings and verdict.
- [x] Verdict values are restricted to the three allowed strings.
- [x] P0 findings must cite an invariant or ADR.
- [ ] Every merged PR has a memo (`DBT-002`; no PRs yet).
- [ ] Every P0/P1 has a resolution or a debt row (`DBT-002`).
