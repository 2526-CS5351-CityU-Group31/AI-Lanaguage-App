# Permission model - baseline R1

**Default rule:** **no read, no write, unless the path and role are explicitly listed below.** A path that is not in this table is denied. A role that is not listed for a path is denied.

**Roles:** `Plan`, `Build`, `Verify` (agent roles from ADR-010) and `Human` (reviewer, content reviewer, release owner). "Read/write" means the agent may use the normal edit tools; "guarded write" means a write is allowed only when the plan is approved, tests exist and a reviewer is named; "append" means new entries only, never edits to existing entries; "no access" means the hook rejects the operation before it reaches the filesystem.

**Enforcement status:** this is a **declared** model. The hooks and `permissions.jsonc` entries are not implemented at baseline; every row's enforcement is tracked by `DBT-003`. A declared row is still a contract: a PR that violates it is rejected in review even before the hook exists.

## 1. Path table

| Path / resource | Plan | Build | Verify | Human required? | Enforced by | Status |
|---|---|---|---|---|---|---|
| `docs/req/requirements.yaml` | read | read | read | yes - baseline/ADR | hook `guard_frozen` | declared |
| `docs/req/req-schema.json` | read | read | read | yes | hook `guard_frozen` | declared |
| `docs/req/prd.yaml` | read | read | read | yes | hook `guard_frozen` | declared |
| `docs/architecture/adr/**` | read | read | read | yes - ADR + append-only | hook `guard_frozen` | declared |
| `architecture-blueprint.md` | read | read | read | yes - ADR | hook `guard_frozen` | declared |
| `docs/architecture/invariants.md` | read | read | read | yes | hook `guard_frozen` | declared |
| `docs/architecture/trace-matrix.md` | read | guarded write (status/evidence cells only) | guarded write (evidence cells only) | yes for row/threshold changes | hook `guard_trace_status` | declared |
| `docs/architecture/memory-design.md` | read | read | read | yes | hook `guard_frozen` | declared |
| `docs/architecture/permission-model.md` | read | read | read | yes | hook `guard_permissions` | declared |
| `docs/architecture/runtime-policy-catalog.md` | read | read | read | yes | hook `guard_frozen` | declared |
| `docs/architecture/evaluation-table.md`, `option-ledger.md`, `risk-list.md` | read | read | read | yes | hook `guard_frozen` | declared |
| `docs/architecture/evaluation-logbook.md` | read | append (dated evidence rows) | append (evidence rows) | yes for threshold changes | hook `guard_logbook_append` | declared |
| `docs/code-governance/structural-constraints.md` | read | read | read | yes | hook `guard_frozen` | declared |
| `docs/code-governance/verification-constraints.md` | read | read | read | yes | hook `guard_frozen` | declared |
| `docs/code-governance/mcp-tool-manifest.md` | read | read | read | yes | hook `guard_manifest` | declared |
| `docs/code-governance/ai-use-log.yaml` | read | append only via `append_ai_session` | read | session owner verifies | hook `guard_ai_log_append` | declared |
| `docs/review-memo.md` | read | read | read | yes - reviewer only | hook `guard_review` | declared |
| `docs/debt-register.md`, `docs/bug-diary.md` | read | append (new rows) | append (new rows) | yes for closing a row | hook `guard_append_only` | declared |
| `docs/README.md` | read | guarded write | read | reviewer | hook `guard_docs` | declared |
| `src/response_validator.py` | read | **no access** | read | yes - human author + ADR | hook `guard_authority_module` | declared |
| `src/ownership_guard.py` | read | **no access** | read | yes - human author + ADR | hook `guard_authority_module` | declared |
| `src/degradation_controller.py` | read | **no access** | read | yes - human author + ADR | hook `guard_authority_module` | declared |
| `src/tutor_pipeline.py` | read | guarded write | read | yes - gate order change | hook `guard_gate_call` | declared |
| `src/retrieval_service.py` | read | guarded write | read | yes - filter change | hook `guard_retrieval_filter` | declared |
| `src/content_publisher.py` | read | guarded write | read | yes - publish semantics | hook `guard_content_publisher` | declared |
| `src/assessment_service.py`, `src/progress_ledger.py` | read | guarded write | read | yes - score/event semantics | hook `guard_record_path` | declared |
| `src/config.py` | read | guarded write | read | yes - new env key + config doc | hook `guard_config` | declared |
| `src/**` (all other modules) | read | guarded write | read | plan approval + reviewer | `permissions.jsonc` | declared |
| `src/contracts/**`, `src/db/**` | read | guarded write | read | reviewer | `permissions.jsonc` | declared |
| `frontend/**` | read | guarded write | read | reviewer | `permissions.jsonc` | declared |
| `test/structural/**`, `test/offline/**`, `test/live/**` | read | guarded write only after test approval | read/append evidence | approval artifact (`G2`) | hook `guard_test_approval` | declared |
| `scripts/validate_req.py`, `scripts/check_*.py`, `scripts/run_eval.py` | read | **no access** | read | yes - gate integrity | hook `guard_gate_scripts` | declared |
| `scripts/**` (other) | read | guarded write | read | reviewer | `permissions.jsonc` | declared |
| `migrations/**` | read | guarded write before first apply; **no access** after merge | read | reviewer + rollback plan | hook `guard_migrations` | declared |
| `prompts/**` | read | **no access** | read | yes - prompt owner + ADR | hook `guard_prompt` | declared |
| `content/**` | read | **no access** | read | yes - content reviewer | hook `guard_content` | declared |
| `evals/**` | read | read | read (run only) | yes - evaluation owner | hook `guard_eval_set` | declared |
| `transcripts/**` | **no access** | **no access** | **no access** | humans only | hook `guard_transcripts` | declared |
| `.github/workflows/**` | read | **no access** | read | yes | hook `guard_ci` | declared |
| `.opencode/permissions.jsonc`, `.agent/rules.md` | read (no config) | **no access** | **no access** | yes | hook `guard_agent_config` | declared |
| `AGENTS.md`, `Prompt.md`, `Report.md` | read | read | read | yes - human author | hook `guard_frozen` | declared |
| `README.md`, `docker-compose.yml`, `.env.example`, `pyproject.toml`, `frontend/package.json` | read | guarded write | read | dependency change needs an ADR | `permissions.jsonc` | declared |
| `.env`, `.env.*` (except `.env.example`), any secret file | **no access** | **no access** | **no access** | humans via secret store only | hook `guard_secret` | declared |
| `reports/**`, `.pytest_cache/**`, test temp files | read | write | write | no | `permissions.jsonc` | declared |
| Any path not listed | **no access** | **no access** | **no access** | yes | default deny | declared |

**Coverage note:** every directory in the blueprint's filesystem tree appears above, or is covered by an explicit wildcard (`src/**`, `scripts/**`, `reports/**`). A new top-level path is not usable until it is added here and to `permissions.jsonc` in the same PR.

## 2. Invariant-bearing paths

The three modules that contain the validator, the ownership gate and the failure-action switch are **no access** for the Build agent. They are the paths where a one-line change can silently disable an invariant:

| Path | Invariant(s) | Why human-only | Change process |
|---|---|---|---|
| `src/response_validator.py` | INV-001, INV-002, INV-007 | The gate itself; a "small fix" can turn a rejection into a pass-through | Human author, ADR-005 reference, failing-before/passing-after test, two reviewers |
| `src/ownership_guard.py` | INV-003 | The isolation gate; a default-allow branch exposes every learner | Human author, ADR-001 reference, 20-probe negative suite, two reviewers |
| `src/degradation_controller.py` | INV-006, INV-008, NFR-006 | The failure switch; a wrong branch can bypass validation on an error path | Human author, runtime policy row, fault-injection test, two reviewers |

Other invariant-enforcing modules are **guarded write**, not no-access: `TutorPipeline`, `RetrievalService`, `ContentPublisher`, `AssessmentService`, `ProgressLedger`, `SessionSummaryStore`, `ObservabilityStore`, `PromptAssembler`. They are buildable, but a change to their enforcement logic requires an approved plan, a named test and a reviewer who is not the author. This is a deliberate balance: the gate code is human-authored, the surrounding services are agent-buildable under guard.

## 3. Enforcement mapping

| Row group | Machine artifact | Check | Failure behaviour |
|---|---|---|---|
| Default deny + allowlist | `.opencode/permissions.jsonc` | `scripts/check_permissions.py` compares the effective config to this table's manifest | Merge blocked; hook denies with `PATH_NOT_ALLOWED` |
| Frozen docs/ADR/blueprint | `guard_frozen` hook | `git diff --name-only` against a frozen list | Write rejected; agent must open an ADR |
| Authority modules | `guard_authority_module` hook | Path match + caller role | `HUMAN_ONLY`; attempt recorded |
| Prompts/content | `guard_prompt`, `guard_content` | Path + publisher role | `HUMAN_ONLY`; content publish requires a reviewer |
| CI/gates | `guard_ci`, `guard_gate_scripts` | Path match | `HUMAN_ONLY`; branch protection still applies |
| Test approval | `guard_test_approval` | Approval artifact precedes the commit | Write rejected; plan must be approved first |
| Migrations | `guard_migrations` | Applied migrations are immutable; backup proof | `FROZEN_PATH`; new migration required |
| AI log | `guard_ai_log_append` | Append-only diff + schema | Rejected; session must use the tool |
| Secrets | `guard_secret` | Filename and content scan | Denied before read/write; security event |
| Drift | `check_permissions.py` | Table vs config isomorphism | Merge blocked; the table is the source of truth |

`permissions.jsonc` is the machine-readable source; this table is the human-readable contract. `scripts/check_permissions.py` (planned, `DBT-003`) must fail when they differ, not warn. A row without a machine mapping is a wish, and the status column is there to keep that visible until Sprint 2.

## 4. Violation handling

1. **Block:** the hook rejects the operation before the write, returns `PATH_NOT_ALLOWED`, `HUMAN_ONLY` or `APPROVAL_MISSING`, and leaves the working tree unchanged.
2. **Record:** append to `reports/permission-denials.jsonl` with timestamp, role, path, operation, reason and session id. No file content is recorded.
3. **Notify:** Member 5 (QA & Governance) is notified for any `HUMAN_ONLY` attempt; the session owner is notified for `APPROVAL_MISSING`.
4. **Stop on repetition:** three denials in one session stop the agent session and require a re-plan. This is a safety valve against a loop that tries variants of the same forbidden write.
5. **Review:** a denial is not a failure of the agent alone; if the plan required a forbidden write, the plan was wrong and must be revised.

## 5. Emergency path

- **Who:** the release owner (Member 5 at baseline) or the on-call human, never an agent.
- **When:** a production incident requires a hotfix to a protected path, or a rollback cannot wait for the normal ADR cycle.
- **What:** a break-glass write is allowed only with a recorded incident id, a two-person approval and a rollback plan. The change is annotated in the commit message with `BREAK-GLASS: <incident>`.
- **Record:** an entry in `docs/code-governance/ai-use-log.yaml`, a `review-memo.md` memo and an `evaluation-logbook.md` row within 24 hours; an ADR within 5 working days.
- **Limit:** the emergency path may not disable an invariant test, remove a citation check or grant a model tool access. Those are not hotfixes; they are re-architecture.

## 6. Done-when status

- [x] Every path in the repository tree is listed or covered by an explicit wildcard (45 rows including the default-deny row).
- [x] The three gate modules are exactly the `no access` rows; other invariant services are guarded write with a named reason.
- [ ] `permissions.jsonc` and this table are isomorphic and `scripts/check_permissions.py` fails on drift (`DBT-003`).
- [ ] Hooks `guard_frozen`, `guard_authority_module`, `guard_prompt`, `guard_content`, `guard_ci`, `guard_migrations`, `guard_secret`, `guard_test_approval`, `guard_ai_log_append` are implemented (`DBT-003`).
- [ ] A deliberate denial is demonstrated in a safe branch and preserved as evidence (`DBT-003`).
