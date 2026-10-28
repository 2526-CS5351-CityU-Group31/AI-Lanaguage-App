# MCP tool manifest - baseline R1, version 1.0.0

**Derivation statement:** this manifest is **generated from** the accepted ADRs and the permission model - one tool per enforceable constraint that needs a typed boundary. It is not a wish list and not a description of every function. A tool exists only if an ADR clause names the boundary it enforces; a tool without an ADR source is a defect caught by `scripts/check_manifest.py` (planned, `DBT-005`).

**Surfaces:**

- **R - runtime:** an internal, typed operation exposed to the application components. The allowed caller is exactly one owning element; the model never calls these.
- **A - agent:** an operation exposed to the coding-agent environment through the `AgentToolDispatcher`. The dispatcher is the single caller entry; the allowed role list is enforced inside it. Human-only tools are listed here so the dispatcher can reject them explicitly rather than by omission.

**One caller rule:** every row has exactly **one** allowed caller. Multiple callers mean the boundary is not a boundary. For agent tools, the caller is the dispatcher; the role list is the dispatcher's authorization rule, not an additional caller.

## 1. Runtime tools

| Tool | Surface | ADR source | Allowed caller (exactly one) | Allowed role(s) | Invariant | Input schema (key fields) | Validates before acting | Rejection behaviour | Side effects / idempotency | Version |
|---|---|---|---|---|---|---|---|---|---|---|
| `issue_session` | R | ADR-001 §Boundaries | ONLY `RequestAuthenticator` | learner, system | INV-003 | `email`, `password`, `request_id` | credentials; rate limit; no `user_id` field; lockout after 5 failures/10 min | `401` generic message; `429` with retry-after | Writes `sessions` + audit; idempotency `request_id` | 1.0.0 |
| `authorize_record_access` | R | ADR-001 §Authority | ONLY `OwnershipGuard` | learner, operator | INV-003 | `principal`, `resource_type`, `resource_id`, `action` | owner match; action enum; resource type allowlist | `404` empty body; operator path `403` without audit | Appends security event; idempotency `request_id` | 1.0.0 |
| `persist_profile` | R | ADR-001 §Authority | ONLY `LearnerProfileService` | learner | INV-003 | `principal`, `patch{language, level, goals}` | language = English; level in A1/A2/B1; lengths; owner only | `422` field errors; `403` on foreign profile | Writes `profiles`; idempotency `request_id` | 1.0.0 |
| `persist_session_turn` | R | ADR-005 §Decision | ONLY `PracticeSessionService` | learner | INV-001, INV-006 | `principal`, `session_id`, `turn_request_id`, `learner_text`, `validated_response`, `validation_id` | accepted verdict; owner; input <= 1,500 chars; unique turn | `409` duplicate returns prior; `404` foreign session; `422` invalid | Writes `messages` + learning event + audit in one transaction; idempotency `(user_id, turn_request_id)` | 1.0.0 |
| `persist_writing_feedback` | R | ADR-005 §Response contracts | ONLY `WritingFeedbackService` | learner | INV-001 | `principal`, `submission_id`, `original_fingerprint`, `validated_suggestion`, `validation_id` | accepted verdict; original fingerprint unchanged; length caps | `409` conflict on original change; `422` invalid | Writes `feedback` only; original row immutable; idempotency `submission_id` | 1.0.0 |
| `persist_vocabulary_entry` | R | ADR-008 §Event model | ONLY `VocabularyService` | learner | INV-003 | `principal`, `word`, `sense`, `decision` (`confirm`/`dismiss`), `source_ref` | explicit confirmation; dedupe `(user, word, sense)`; level match | `409` duplicate returns existing; `422` invalid sense | Writes `user_vocabulary`; idempotency `(user_id, word, sense)` | 1.0.0 |
| `persist_quiz_score` | R | ADR-008 §Scoring rules | ONLY `AssessmentService` | learner, system | INV-004 | `principal`, `attempt_id`, `responses[]`, `client_score?` | key loaded server-side; `client_score` ignored; one attempt; option ids valid | `422` invalid response; `409` already scored | Writes `attempts` + learning event; idempotency `(user_id, attempt_id)` | 1.0.0 |
| `append_learning_event` | R | ADR-008 §Event model | ONLY `ProgressLedger` | system | INV-005 | `principal`, `event_type`, `ref_id`, `occurred_at`, `request_id` | event enum; owner; append-only; no raw text | `409` duplicate; `422` unknown event | Appends `learning_events`; idempotency `(user_id, event_type, ref_id)` | 1.0.0 |
| `publish_content_version` | R | ADR-007 §Publication model | ONLY `ContentPublisher` | reviewer, operator | INV-008, INV-009 | `actor`, `version_id`, `manifest_hash`, `reviewer` | licence, reviewer, checksum, one active version, no learner text | `422` incomplete manifest; `409` active conflict; `403` non-reviewer | Writes `content_versions` + audit; idempotency `version_id` | 1.0.0 |
| `persist_session_summary` | R | ADR-009 §Store inventory | ONLY `SessionSummaryStore` | system | INV-011 | `principal`, `summary_text`, `token_count`, `turn_range` | <= 400 tokens; owner; no direct quote > 200 chars | `422` over length/scope | Writes `session_summaries`; idempotency `summary_version` | 1.0.0 |
| `emit_audit_event` | R | ADR-009 §Privacy rules | ONLY `ObservabilityStore` | system | INV-010 | `request_id`, `event_type`, `fields` (allowlist), `user_ref_hash` | field allowlist; hash; no raw text; event enum | `422` unknown field -> drop field + security alert | Appends `observability_events`; idempotency `(request_id, event_type)` | 1.0.0 |
| `call_model_provider` | R | ADR-005 §Decision; ADR-006 §Assembly | ONLY `ModelGateway` | system | INV-001, INV-006 | `request_id`, `prompt`, `schema_id`, `token_budget`, `task` | daily cap; timeout; retry <= 2; circuit state; schema id | `429` cap; `503` circuit open; typed provider error | External call + `ai_usage_daily`; budget counted once per `request_id` | 1.0.0 |
| `retrieve_published_evidence` | R | ADR-007 §Ingestion and activation flow | ONLY `RetrievalService` | system | INV-008 | `query`, `language`, `level`, `topic`, `top_k` (<= 10) | active/published only; language/level/topic pre-filter; dedupe | Empty `EvidenceSet` (not an exception) | Read-only; idempotency `query_hash` | 1.0.0 |
| `validate_tutor_output` | R | ADR-005 §Decision | ONLY `ResponseValidator` | system | INV-001, INV-002, INV-007 | `task`, `output`, `evidence` | schema, citation subset, lengths, abstention, unknown/tool fields | Typed `Verdict` (rejected), never a raised exception | None; returns `validation_id` | 1.0.0 |

## 2. Agent tools

| Tool | Surface | ADR source | Allowed caller (exactly one) | Allowed role(s) | Invariant | Input schema (key fields) | Validates before acting | Rejection behaviour | Side effects / idempotency | Version |
|---|---|---|---|---|---|---|---|---|---|---|
| `read_registry_slice` | A | ADR-010 §Roles and powers | ONLY `AgentToolDispatcher` | Plan, Build, Verify | INV-001 | `ids[]`, `fields[]` | ids resolve; field allowlist; read-only | `422` unknown id/field | None | 1.0.0 |
| `validate_registry` | A | ADR-010 §Roles | ONLY `AgentToolDispatcher` | Plan, Build, Verify | INV-005 | `path` (fixed to `docs/req/requirements.yaml`) | schema + cross-record checks; no write | Exit non-zero, typed errors | None (report only) | 1.0.0 |
| `run_structural_checks` | A | ADR-010 §Tool boundary | ONLY `AgentToolDispatcher` | Build, Verify | INV-001, INV-003, INV-006 | `suite` (`structural`), `fail_fast` | role; no network; `src/` read-only | `403 CALLER_NOT_ALLOWED`; exit non-zero | Writes `reports/structural/` only | 1.0.0 |
| `run_offline_suite` | A | ADR-010 §Tool boundary | ONLY `AgentToolDispatcher` | Build, Verify | INV-001 | `suite` (`offline`/`all`), `fail_fast` | stub mode only; rejects live credentials | `403` if live requested | Writes `reports/` and `.pytest_cache/` | 1.0.0 |
| `run_eval_replay` | A | ADR-010 §Approval gates | ONLY `AgentToolDispatcher` | Verify (live also requires human approval) | INV-002, INV-008 | `mode` (`offline`/`live`), `suite`, `approval_id` | suite version frozen; live requires approval id + capped key | `403 HUMAN_ONLY` for live without approval; `422` unknown suite | Writes `reports/eval/`; no repo mutation | 1.0.0 |
| `append_ai_session` | A | ADR-010 §Responsibility map | ONLY `AgentToolDispatcher` | Build, Verify | INV-010 | `session_id`, `pr`, `stage`, `agent`, `model`, `prompt_ref`, `inputs`, `outputs`, `interventions` | append-only; unique session; schema; no secrets/raw text | `409` duplicate session; `422` invalid field | Appends `docs/ai-use-log.yaml`; idempotency `session_id` | 1.0.0 |
| `record_plan_approval` | A | ADR-010 §Approval gates G1/G2 | ONLY `AgentToolDispatcher` | **Human only** | INV-006 | `plan_revision`, `requirement_ids[]`, `tests[]`, `approver`, `approved_at`, `rollback` | human principal; named approver; tests exist in plan; timestamp | `403 HUMAN_ONLY` for any agent principal | Writes approval artifact + audit | 1.0.0 |
| `write_frozen_path` | A | ADR-010 §Approval gates G3 | ONLY `AgentToolDispatcher` | **Human only** | INV-001 | `path`, `adr_ref`, `approval_id`, `reason`, `diff` | path is frozen; ADR accepted; two-person approval | `403 HUMAN_ONLY`; `409` missing ADR | Writes frozen path + audit + log entry | 1.0.0 |
| `apply_migration` | A | ADR-010 §Tool boundary | ONLY `AgentToolDispatcher` | Build | INV-005 | `migration_id`, `backup_id`, `dry_run` | backup exists; one migration; applied migrations immutable | `409` already applied; `422` missing backup | Applies schema + audit; idempotency `migration_id` | 1.0.0 |
| `ingest_content_dry_run` | A | ADR-007 §Ingestion and activation flow; ADR-010 | ONLY `AgentToolDispatcher` | Plan, Build, Human content reviewer | INV-009 | `manifest_path` (must be under `content/`), `mode` (`dry-run` only) | licence/reviewer fields; no learner path; no DB write | `422` invalid manifest; `403` outside `content/` | Writes `reports/ingest_report.json` only | 1.0.0 |

## 3. Prohibited calls

| Prohibited pair | Why | Check |
|---|---|---|
| A circuit breaker, rate limiter or retry wrapper around `ResponseValidator`, `OwnershipGuard`, `AssessmentService` or `ProgressLedger` | The gate must run on every attempt, including failure paths; wrapping it can skip it | import-linter + AST; `test/structural/test_authority_imports.py` |
| Any caller other than `TutorPipeline` importing `ResponseValidator` | The gate has one call site | import-linter C1 |
| Any module other than `ObservabilityStore` appending to the audit store | Audit integrity and redaction | S6 single-writer + DB grants |
| Any module other than `ProgressLedger` appending to `learning_events` | Event log is the record of truth | S6 + grants |
| `SessionSummaryStore` imported by `AssessmentService`, `ProgressLedger`, `OwnershipGuard`, `RequestAuthenticator` or `ContentPublisher` | Memory must not influence decisions | ADR-009 C7 import contract |
| An agent calling `record_plan_approval`, `write_frozen_path` or a live `run_eval_replay` without approval | Human gates would be decorative | dispatcher `HUMAN_ONLY`/`APPROVAL_MISSING` |
| An agent tool opening a database connection or reading `.env` | Tool boundary is the only mutation path | dispatcher static allowlist + `guard_secret` |
| A model call outside `ModelGateway` (direct HTTP/SDK use in a service) | Budget, timeout, retry and schema live in one adapter | grep for provider SDK imports outside `model_gateway.py` |
| Publishing content outside `ContentPublisher` | Version/activation invariant | DB grants + code review |
| Raw learner text in an audit event | INV-010 | field allowlist test + 100-event sample |

## 4. Filtered manifest for revision builds

| Version | Change | Removed tools | Added tools | Agent restriction |
|---|---|---|---|---|
| 1.0.0 (R1) | Initial manifest | none | all 24 rows | R1 only |
| Next revision | A removed tool is listed as `REMOVED` with the ADR that retired it; the dispatcher rejects it with `TOOL_RETIRED` | listed per revision | listed per revision | An agent may not call a removed tool, even if it remembers the old schema |

Rules for a revision:

- Bump the minor version for an additive, backward-compatible tool; bump the major version for a removed or schema-breaking change.
- A removed tool's row stays in the manifest with status `removed`; deleting the row hides the fact that an agent may still try it.
- The filtered manifest is generated per build round and included in the plan approval artifact.

## 5. Done-when status

- [x] Every tool maps to exactly one ADR section and at least one invariant.
- [x] Every side-effecting element in the blueprint has exactly one runtime tool: 12 of 19 elements; the other 7 have no direct side effect.
- [x] Every allowed-caller list has exactly one entry.
- [x] A reviewer can answer "may the Build agent call this?" from the Surface/Allowed role columns without opening code.
- [ ] `scripts/check_manifest.py` exists and fails on a tool with no ADR, no invariant or two callers (`DBT-005`).
- [ ] The dispatcher enforces the human-only rows and records rejected attempts (`DBT-005`).
