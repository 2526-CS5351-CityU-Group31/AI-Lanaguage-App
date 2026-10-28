# Trace matrix - baseline R1 (design view)

**Status of this view:** every row is `design` on 2026-10-27. No implementation exists yet; `planned:` means the test or command is designed and its path is reserved, but the file is not in the repository until the build round. Those gaps are tracked once as `DBT-003`, not hidden per row.

**Coverage rule:** the matrix has exactly one row per requirement in `docs/req/requirements.yaml` (39 rows: 36 `must`, 3 `should`, 18 ASR). No orphans in either direction. `scripts/check_trace.py` (planned) enforces the row count and the REQ id set.

**Status vocabulary:** `design` -> `implemented` -> `tested`. A row may not move to `tested` unless the named test exists at the named path and passes. A retired requirement keeps its row and changes status to `retired` first.

**Evidence legend:** `planned:` = designed but not yet in the repo (`DBT-003`); `gate:` = CI script to be written; `none` = no runtime monitor, with a justification in the cell.

| REQ | Type | Status | Cluster | Architectural consequence | Enforcing component | Test / evidence | Runtime monitor |
|---|---|---|---|---|---|---|---|
| REQ-LANG-ARCH-001 | architectural_constraint | design | CL-AUTHORITY | One validation gate; validator import restricted to the tutor pipeline | `ResponseValidator` | planned: `test/structural/test_authority_imports.py::test_single_validation_gate` | `validation_reject_total`, `validation_bypass_count` |
| REQ-LANG-INV-001 | invariant | design | CL-AUTHORITY | Advisory -> validator -> persistence is a one-way flow | `ResponseValidator.validate_output()` | planned: `test/offline/invariants/test_inv_001_no_unvalidated_output.py` | `unvalidated_output_total` (must stay 0) |
| REQ-LANG-INV-002 | invariant | design | CL-AUTHORITY | Retrieved evidence is an input to validation; citations rendered from server metadata | `ResponseValidator.validate_citations()` | planned: `test/offline/invariants/test_inv_002_citation_provenance.py` | `citation_reject_total`, `citation_bypass_total` |
| REQ-LANG-SEC-001 | security | design | CL-AUTHORITY | Untrusted evidence block; no tool schema in the prompt; constraints restated after evidence | `PromptAssembler.assemble()` | planned: `test/offline/invariants/test_inv_007_retrieved_text_is_data.py` | `injection_escape_total` (must stay 0) |
| REQ-LANG-ARCH-002 | architectural_constraint | design | CL-AUTHORITY | `TutorPipeline` excluded from the database package; persistence is a separate call | `TutorPipeline.handle_turn()` | planned: `test/structural/test_authority_imports.py::test_tutor_pipeline_read_only` | `tutor_pipeline_db_writes` (must stay 0) |
| REQ-LANG-SEC-002 | security | design | CL-ISOLATION | Owner-scoped repository boundary; 404 for foreign records | `OwnershipGuard.authorize()` | planned: `test/offline/invariants/test_inv_003_cross_user_isolation.py` | `cross_user_exposure_total`, `cross_user_denial_total` |
| REQ-LANG-INV-003 | invariant | design | CL-ISOLATION | Principal comes only from the authenticated session | `RequestAuthenticator` | planned: `test/offline/invariants/test_inv_003_cross_user_isolation.py::test_identity_not_from_payload` | `identity_spoof_attempts` |
| REQ-LANG-FR-001 | functional | design | CL-ISOLATION | Identity boundary and profile store | `LearnerProfileService` | planned: `test/offline/test_auth_profile.py` | `auth_failure_total` |
| REQ-LANG-FR-002 | functional | design | CL-ISOLATION | Immutable session owner; server-assigned turn order | `PracticeSessionService` | planned: `test/offline/test_session_ownership.py` | `session_owner_mutation_total` (0) |
| REQ-LANG-SEC-003 | security | design | CL-ISOLATION | `AppConfig` is the only `os.environ` reader; secrets not bundled | `AppConfig` | planned: `scripts/scan_secrets.py --scope repo,frontend/dist,logs --sample 100` | `secret_scan_findings` (0) |
| REQ-LANG-SEC-004 | security | design | CL-ISOLATION | Curriculum store and learner store are separate; no learner text in the index | `ContentPublisher.ingest()` | planned: `test/offline/invariants/test_inv_009_privacy_boundary.py` + `test_inv_010_redaction.py` | `learner_text_in_shared_stores` (0), `redaction_failure_total` (0) |
| REQ-LANG-FR-003 | functional | design | CL-GROUNDING | Retrieval and citation-rendering path; source metadata from the database | `RetrievalService` | planned: `python scripts/run_eval.py --suite evals/EVAL-1.0.0.yaml --offline --case-type grounded --check citations` | `grounded_answer_total`, `citation_render_total` |
| REQ-LANG-FR-004 | functional | design | CL-GROUNDING | Abstention branch owned by the degradation controller | `DegradationController` | planned: `python scripts/run_eval.py --suite evals/EVAL-1.0.0.yaml --offline --case-type abstain --check abstention` | `no_evidence_total`, `abstention_total` |
| REQ-LANG-ARCH-003 | architectural_constraint | design | CL-GROUNDING | Published/language/level/topic filters run before ranking | `RetrievalService.search()` | planned: `test/offline/invariants/test_inv_008_published_only.py` | `unpublished_chunk_served` (0) |
| REQ-LANG-NFR-001 | quality | design | CL-GROUNDING | Chunking, top-5 retrieval, reranking | `RetrievalService` | planned: `python scripts/run_eval.py --suite evals/EVAL-1.0.0.yaml --offline --metric recall_at_5` | `retrieval_recall_at_5` (nightly on fixed set) |
| REQ-LANG-NFR-002 | quality | design | CL-GROUNDING | Citation gate and server-rendered metadata | `ResponseValidator` | planned: `python scripts/run_eval.py --suite evals/EVAL-1.0.0.yaml --offline --metric citation_validity` | `citation_validity` (release gate) |
| REQ-LANG-NFR-003 | quality | design | CL-GROUNDING | Human-scored evaluation set with two reviewers | `TutorPipeline` (evaluated output) | planned: `python scripts/run_eval.py --suite evals/EVAL-1.0.0.yaml --metric grounded_correctness --human-scored` | `grounded_correctness` (eval run) |
| REQ-LANG-PERF-001 | performance | design | CL-GROUNDING | HNSW index and query plan on the active chunks | `RetrievalService` | planned: `python scripts/bench_retrieval.py --chunks 1000 --concurrency 5 --runs 50` | `retrieval_p95_ms` |
| REQ-LANG-FR-005 | functional | design | CL-RECORD | Original and suggestion stored separately; suggestion labelled | `WritingFeedbackService` | planned: `test/offline/test_writing_feedback.py` | `silent_overwrite_total` (0) |
| REQ-LANG-FR-006 | functional | design | CL-RECORD | Confirmation state machine; unique `(user_id, word, sense)` | `VocabularyService` | planned: `test/offline/test_vocabulary.py` | `unconfirmed_mastery_total` (0) |
| REQ-LANG-FR-007 | functional | design | CL-RECORD | Server-held answer keys; key never in the client model | `AssessmentService` | planned: `test/offline/test_quiz_contract.py` | `ambiguous_quiz_item_served` (0) |
| REQ-LANG-INV-004 | invariant | design | CL-RECORD | Request model excludes `score`; scoring is a server function | `AssessmentService.score_attempt()` | planned: `test/offline/invariants/test_inv_004_backend_scoring.py` | `client_score_acceptance_total` (0) |
| REQ-LANG-FR-008 | functional | design | CL-RECORD | Dashboard projection over `learning_events` | `ProgressLedger.project_progress()` | planned: `test/offline/test_progress_projection.py` | `dashboard_projection_errors` |
| REQ-LANG-INV-005 | invariant | design | CL-RECORD | Event log is the single source of truth for totals | `ProgressLedger.project_progress()` | planned: `test/offline/invariants/test_inv_005_progress_parity.py` | `progress_total_mismatch_total` (0) |
| REQ-LANG-FR-009 | functional | design | CL-RECORD | Bounded user-scoped summary; context-only | `SessionSummaryStore` | planned: `test/offline/test_session_summary.py` + `test/offline/invariants/test_inv_011_summary_isolation.py` | `summary_scope_violation_total` (0) |
| REQ-LANG-NFR-004 | quality | design | CL-RESILIENCE | 25 s provider timeout, fixed context budget, bounded retries | `TutorPipeline` / `ModelGateway` | planned: `python scripts/bench_tutor_latency.py --turns 30 --env reference` | `ai_turn_latency_seconds` p95 |
| REQ-LANG-NFR-005 | quality | design | CL-RESILIENCE | Checkpoint + retry state; completion stays false on failure | `PracticeSessionService` | planned: `test/offline/test_degradation.py` | `failed_turn_completion_total` (0) |
| REQ-LANG-INV-006 | invariant | design | CL-RESILIENCE | Fail-closed orchestration; no raw text on the failure path | `TutorPipeline.handle_turn()` | planned: `test/offline/invariants/test_inv_006_no_safety_bypass.py` | `safety_bypass_total` (0) |
| REQ-LANG-NFR-006 | quality | design | CL-RESILIENCE | Retrieval-outage abstention route | `DegradationController` | planned: `test/offline/test_degradation.py::test_retrieval_unavailable` | `retrieval_failure_abstention_rate` |
| REQ-LANG-COST-001 | cost | design | CL-COST | Per-user call counter and server-side cap in the model gateway | `ModelGateway` | planned: `test/offline/test_cost_cap.py` | `ai_calls_per_user_day`, `ai_calls_over_cap` (0) |
| REQ-LANG-COST-002 | cost | design | CL-COST | Token accounting per turn and a daily cost series | `ObservabilityStore` | planned: `python scripts/report_cost.py --window 7d --session-size 6` | `session_cost_usd`, `cost_drift_ratio` |
| REQ-LANG-FR-010 | functional | design | CL-EVOLUTION | Versioned publish workflow with provenance and reviewer | `ContentPublisher` | planned: `test/offline/test_content_publish.py` | `publish_state_integrity` (100%) |
| REQ-LANG-GOV-001 | governance | design | CL-EVOLUTION | Atomic version pointer; retired excluded before query | `ContentPublisher.activate()` | planned: `test/offline/invariants/test_inv_008_published_only.py` | `unpublished_chunk_served` (0), `active_version_count` |
| REQ-LANG-GOV-002 | governance | design | CL-EVOLUTION | Audit event field allowlist; version metadata per turn | `ObservabilityStore.append_turn_event()` | planned: `test/offline/test_observability_metadata.py` | `turn_metadata_completeness` (100%) |
| REQ-LANG-GOV-003 | governance | design | CL-EVOLUTION | Evaluation replay gate in CI for model-facing changes | `scripts/check_eval_gate.py` | planned: `python scripts/check_eval_gate.py --base origin/main --head HEAD` | none - CI gate evidence only |
| REQ-LANG-NFR-007 | quality | design | CL-ACCESS | Accessible component library; five critical flows tested | frontend flows (no backend element) | planned: `npm --prefix frontend run test:a11y` | none - CI gate evidence only |
| REQ-LANG-GOV-004 | governance | design | CL-GOVERNANCE | AI use log gate keyed to session and PR | `scripts/check_ai_log.py` | planned: `python scripts/check_ai_log.py --pr $PR` | none - PR gate evidence only |
| REQ-LANG-GOV-005 | governance | design | CL-GOVERNANCE | Approval artifact precedes implementation | `scripts/check_test_approval.py` | planned: `python scripts/check_test_approval.py --pr $PR` | none - PR gate evidence only |
| REQ-LANG-ARCH-004 | architectural_constraint | design | CL-GOVERNANCE | Scope guard: no routes for deferred capabilities | `test/structural/test_scope.py` | planned: `test/structural/test_scope.py::test_no_out_of_scope_routes` | none - structural gate only |

## Coverage summary

| Dimension | Value | Check |
|---|---|---|
| Rows | 39 | equals requirement count 39 |
| Must rows with non-empty evidence | 36 / 36 | every must names a planned command or test |
| Should rows with non-empty evidence | 3 / 3 | FR-009, PERF-001, NFR-007 |
| ASR rows naming a blueprint element | 18 / 18 | `forces_element` resolves to the component table |
| Invariant rows cross-linked to `invariants.md` | 11 / 11 | each `INV-*` appears in at least one row |
| Rows with a runtime monitor | 34 | 5 governance/CI rows justify `none` |
| Rows whose state is `tested` | 0 | no implementation at baseline |
| Orphans (requirement without row) | 0 | by construction |
| Dead rows (row without requirement) | 0 | by construction |

## Coverage by cluster

| Cluster | Requirements in registry | Rows here | Complete? |
|---|---|---|---|
| CL-AUTHORITY | 5 | 5 | yes |
| CL-ISOLATION | 6 | 6 | yes |
| CL-GROUNDING | 7 | 7 | yes |
| CL-RECORD | 7 | 7 | yes |
| CL-RESILIENCE | 4 | 4 | yes |
| CL-COST | 2 | 2 | yes |
| CL-EVOLUTION | 4 | 4 | yes |
| CL-ACCESS | 1 | 1 | yes |
| CL-GOVERNANCE | 3 | 3 | yes |
| **Total** | **39** | **39** | **yes** |

## Done-when status at baseline

- [x] Row count equals requirement count; zero orphans both ways (by construction; script pending).
- [x] Every `must` requirement has a non-empty test/evidence cell (a planned command).
- [ ] Every row whose status is `tested` names an existing test - no row is `tested` yet.
- [x] New rounds append rows and update status; no row is deleted to hide a retirement.
- [ ] `scripts/check_trace.py` exists and fails on an orphan (`DBT-003`).

## Update protocol

1. A new requirement is added to `requirements.yaml` first, then a row is appended here in the same PR.
2. A test landing changes the row from `design` to `implemented`, then `tested` only after it passes in CI; the PR links the run.
3. A requirement becoming `retired` changes the requirement status first; the row stays with `retired` status and its evidence history.
4. A monitor name change is a one-line edit here and in the runtime policy catalog; no threshold is copied into this file.
