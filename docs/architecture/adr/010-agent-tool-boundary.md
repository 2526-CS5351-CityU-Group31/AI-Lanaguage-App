# ADR-010: Bound agent work to named tools, three roles and human approval gates

- **Status:** Accepted
- **Date:** 2026-10-27
- **Supersedes:** -
- **Decision owner:** Member 5 (QA & Governance) with Member 1 (Requirements & PM)
- **Related requirements:** NFR-GOV-001, NFR-GOV-002, INV-SEC-002, FR-CORP-001
- **Related artifacts:** `docs/code-governance/mcp-tool-manifest.md`, `docs/architecture/permission-model.md`, `.opencode/permissions.jsonc`, `.opencode/rules.md`, `.agent/rules.md`, `AGENTS.md`, `Prompt.md`, `docs/code-governance/ai-use-log.yaml`
- **Review triggers:** `unapproved_implementation_commits > 0`; `ai_log_gap_count > 0`; a manifest/table drift detected by `scripts/check_manifest.py`; a permission-hook denial bypassed; a new tool or role requested; an agent writes a protected path; a transcript is missing for a merged PR.

## Context

The course requires an AI coding agent to plan before coding, stop for human approval, and leave an auditable record. The architectural risk is the "gap problem": a prompt says "do not touch the policy core", but nothing in the environment prevents it, so the agent's compliance depends on the same model that may hallucinate.

The project also has four different agent activities - planning, building, verifying and reviewing - with different legitimate powers. Giving every agent every tool makes the role separation decorative. Giving none makes the work impossible.

## Decision

Define three agent roles (`Plan`, `Build`, `Verify`) and one human approver role. Every agent action that reads a protected artifact or mutates the repository goes through a named tool in `mcp-tool-manifest.md`; each tool has exactly one allowed role, a typed input schema and a rejection behaviour. Tools that approve a plan, write a protected path, publish content, or alter a frozen artifact are **human-only** and cannot be called by an agent.

The manifest is derived from this ADR and the permission model. Direct shell access outside the allowlisted tools is not a supported path; a PR that relies on it is rejected in review.

## Roles and powers

| Role | Purpose | May call | May not call |
|---|---|---|---|
| `Plan` | Read requirements and architecture, produce a bounded plan with IDs, files, interfaces, negative tests and rollback | `read_registry_slice`, `validate_registry`, `run_structural_checks` (read-only), `ingest_content_dry_run` | Any write tool, test execution with live credentials, approval tool |
| `Build` | Implement the approved plan within permissions, add tests, run offline checks | `read_registry_slice`, `validate_registry`, `run_structural_checks`, `run_offline_suite`, `append_ai_session`, `apply_migration`, `run_eval_replay` (offline only) | `record_plan_approval`, `write_frozen_path`, `publish_content`, live eval without human approval |
| `Verify` | Run Tiers 1-3, produce evidence, update trace status and the evaluation logbook | `read_registry_slice`, `validate_registry`, `run_structural_checks`, `run_offline_suite`, `run_eval_replay` (live with approval), `append_ai_session` | Any `src/` write, threshold change, approval tool, content publish |
| `Human approver` | Approve plan, protected paths, ADR, baseline, release | All tools, including `record_plan_approval`, `write_frozen_path`, `publish_content` | Nothing by role; must not self-approve a change they authored |
| Human content reviewer | Review licence and pedagogy, approve offline ingestion | `ingest_content_dry_run`, `publish_content`, `read_registry_slice` | Learner data, source code, CI |

## Approval gates

| Gate | Artifact | Who signs | What it proves | Enforcement |
|---|---|---|---|---|
| G1 Plan approval | Plan artifact with requirement IDs, files, interfaces, negative tests, rollback; recorded in the PR/issue | Human approver | Code follows an approved plan, not a spontaneous agent decision | `scripts/check_test_approval.py` (planned), `NFR-GOV-001` |
| G2 Test approval | Test names and fit criteria listed in the plan; approval predates implementation | Human approver | Tests were designed before they were made to pass | Same script; reviewer verifies timestamp |
| G3 Protected-path write | Human-authored change + ADR reference | Human approver | Authority modules, prompts, CI, permissions and baselines are not agent-editable | `permissions.jsonc` hook `guard_protected_path` |
| G4 Content ingest approval | Manifest with licence, reviewer, checksum | Human content reviewer | Only reviewed, licensed content is ingested and served | `ingest_content_dry_run` tool + `IngestPipeline` (`FR-CORP-001`) |
| G5 Release | Passed Tier 1/2/3 evidence, rollback step, AI log entry | Release owner | A release is evidence-backed and reversible | CI + review memo |

An approval is valid only if it references the plan revision it approved. A materially changed plan requires a new approval; appending implementation detail inside the approved scope does not.

## Tool boundary

- **Read-only context tools** (`read_registry_slice`, `validate_registry`, `ingest_content_dry_run`): no mutation; a dry run may write a report file only under `reports/`.
- **Validation tools** (`run_structural_checks`, `run_offline_suite`): no source mutation; may write test output under `.pytest_cache/` and `reports/`.
- **Evidence tools** (`run_eval_replay`, `append_ai_session`): write evidence artifacts only; `append_ai_session` is append-only and validates the session schema.
- **Mutation tools** (`apply_migration`): guarded by a backup, a dry run and a human-approved plan; one migration at a time.
- **Human-only tools** (`record_plan_approval`, `write_frozen_path`, `publish_content`): the dispatcher rejects any agent principal with `403 HUMAN_ONLY`, records the attempt and notifies the owner.

Every tool's rejection behaviour is typed (`SCHEMA_INVALID`, `CALLER_NOT_ALLOWED`, `HUMAN_ONLY`, `FROZEN_PATH`, `APPROVAL_MISSING`, `BUDGET_EXCEEDED`). A rejection is not retried with a different tool; the agent must change the plan or ask a human.

## Rationale

- The gap problem is closed by an enforcement point, not by a stronger prompt. A tool allowlist is a machine-checkable boundary; "please do not edit the validator" is not.
- Three roles map to the lecture's Plan/Build/Verify separation and to the course's evidence pipeline. A single agent with all powers would erase the separation the report must demonstrate.
- Human-only tools make the approval a record, not a ritual. The timestamp and the plan revision are the evidence.
- A single manifest prevents tool drift: adding a tool requires an ADR clause, a schema, a caller and a test.
- Typed rejections give the agent a deterministic next action and give the reviewer a log of attempts.

## Alternatives considered

| Option | Failed criterion | Evidence |
|---|---|---|
| Unrestricted shell and file access for every agent | Enforcement: a protected path is only protected by the model's willingness to obey | `evaluation-table.md` C4; `NFR-GOV-001` |
| Agent self-approval of its own plan | Authority separation: the planner and approver are the same principal; the gate becomes a formality | G1, `NFR-GOV-001` |
| Hand-written tool list without an ADR source | Maintainability: tools drift from architecture and no one can say why a tool exists | `mcp-tool-manifest.md` derivation rule |
| Fully autonomous multi-agent build | Reviewability: no single approved plan or responsible human; the course requires a human gate | `Prompt.md` D9, `NFR-GOV-002` |
| One role for plan, build and verify | Test independence: the builder verifies its own work and can relax a threshold | G2/G3, `verification-constraints.md` V2 |

## Responsibility map

| Element | Responsibility | Implemented in |
|---|---|---|
| Tool dispatcher (agent environment) | Enforce caller allowlist, schema and human-only rejection | `.opencode/` hook + `scripts/tool_dispatch.py` (planned) |
| `scripts/check_test_approval.py` | Verify approval artifact precedes implementation | `scripts/` (planned, `DBT-003`) |
| `scripts/check_manifest.py` | Detect manifest/ADR/caller drift | `scripts/` (planned, `DBT-003`) |
| Human reviewer | Approve plan, protected paths, content, release | PR review + `docs/review-memo.md` |
| `docs/code-governance/ai-use-log.yaml` | Record session, model, inputs, outputs, interventions | `append_ai_session` tool |

## Quality attribute tradeoffs

| Attribute | Tactic | Buys | Costs | Metric that would invalidate |
|---|---|---|---|---|
| Safety | Tool allowlist + human-only tools | Protected paths are enforced, not requested | More setup and rejected attempts | any protected-path write |
| Auditability | One session entry per agent session + approval artifact | Traceable decisions | Human maintenance burden | `ai_log_gap_count > 0` |
| Velocity | Parallel Plan/Build/Verify within gates | Work proceeds without a meeting per commit | Approval latency at G1 | plan approval > 1 working day |
| Test independence | Separate Verify role; builder cannot approve own plan | Evidence is not self-certified | Extra handoff | verification finds a P0 the builder missed |
| Maintainability | Tools derived from ADR clauses | Tool surface stays small | Every new tool costs a schema and test | manifest drift |

## Consequences

**Benefits**

- The "do not touch the validator" rule now has a hook and a tool rejection, not just a sentence.
- The report can show a real human intervention at a named gate, with a plan revision and a timestamp.
- Role separation makes the verification evidence credible; the builder does not mark its own homework.
- Tool schemas double as documentation for the next agent.

**Costs**

- Initial tool scaffolding (dispatcher, hooks, approval artifact) is work before the first feature.
- A human must be available at G1/G3/G4; a missing approver blocks the build.
- Agents will hit `CALLER_NOT_ALLOWED` and need a re-plan, which costs a turn.
- The manifest is another artifact to keep in sync; drift is a gate failure.

## Review triggers

| Trigger | Threshold | Action |
|---|---|---|
| Unapproved implementation | any occurrence | Revert, re-plan, add a gate test |
| Protected-path attempt | any occurrence | Alert owner; review the tool allowlist |
| Manifest drift | any `check_manifest.py` failure | Block merge; update ADR or manifest |
| New tool requested | any | Add ADR clause, schema, caller, test first |
| Approval latency | > 1 working day for a sprint | Rebalance reviewer rotation |

## Change log

| Date | Change | Evidence |
|---|---|---|
| 2026-10-27 | Initial agent boundary accepted at baseline R1 | `evaluation-logbook.md` 2026-10-27; `permission-model.md` |
| 2026-11-02 | Remapped to SSOT IDs (NFR-GOV-001/002, INV-SEC-002, FR-CORP-001); G4 reframed to ingest approval | This consolidation; `trace-matrix.md` NFR-GOV-001 / NFR-GOV-002 rows |
