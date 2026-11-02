# Trace matrix - baseline R1 (design view)

**Status of this view:** every row is `design`. No implementation exists yet; `planned:` means the test or command is designed and its path is reserved, but the file is not in the repository until the build round. Gaps are tracked once as `DBT-003`, not hidden per row.

**Coverage rule:** the matrix has exactly one row per requirement in `docs/req/requirements.yaml` (31 rows: 30 `Must`, 1 `Should`; types: 13 `invariant`, 9 `functional`, 9 NFR). No orphans in either direction.

**Status vocabulary:** `design` -> `implemented` -> `tested`. A row may not move to `tested` unless the named test exists at the named path and passes. A retired requirement keeps its row and changes status to `retired` first.

**Evidence legend:** `planned:` = designed but not yet in the repo (`DBT-003`); `gate:` = CI script to be written; `none` = no runtime monitor, with a justification in the cell.

| REQ | Type | Status | Enforcing component | Test / evidence | Owner | Runtime monitor |
|---|---|---|---|---|---|---|
| INV-SCOPE-001 | invariant | design | `src/backend/safety_boundary/scope_guard.py` | planned: `test/offline/test_safety_boundary/test_scope_guard.py::test_scope_pipeline_execution_order` | Member 3 (Kapo) | `scope_result_logged_total` (must equal request count) |
| INV-SCOPE-002 | invariant | design | `src/backend/safety_boundary/scope_guard.py` | planned: `test/offline/test_safety_boundary/test_scope_guard.py::test_fixed_refusal_response` | Member 3 (Kapo) | `fixed_refusal_total` |
| INV-SCOPE-003 | invariant | design | `src/backend/api/routers/chat.py` | planned: `test/offline/test_safety_boundary/test_scope_guard.py::test_zero_calls_on_rejection` | Member 3 (Kapo) | `downstream_calls_on_rejection_total` (must stay 0) |
| INV-SCOPE-004 | invariant | design | `src/backend/safety_boundary/scope_guard.py` | planned: `test/offline/test_safety_boundary/test_scope_guard.py::test_uncertain_intent_clarification` | Member 3 (Kapo) | `uncertain_intent_total` |
| INV-SCOPE-005 | invariant | design | `src/backend/safety_boundary/scope_guard.py` | planned: `test/offline/test_safety_boundary/test_scope_guard.py::test_mixed_intent_blocking` | Member 3 (Kapo) | `mixed_intent_block_total` |
| INV-SCOPE-006 | invariant | design | `src/backend/ai_companion/retrieval_adapter.py` | planned: `test/offline/test_ai_companion/test_retrieval_conditions.py::test_conditional_retrieval_routing` | Member 2 (Leon) | `ungrounded_retrieval_total` (must stay 0) |
| INV-AUTH-001 | invariant | design | `src/backend/auth/security.py` | planned: `test/offline/test_auth/test_authorization.py::test_cross_user_isolation` | Member 3 (Kapo) | `cross_user_denial_total`, `cross_user_exposure_total` (0) |
| INV-LANG-001 | invariant | design | `src/backend/api/schemas/profile.py` | planned: `test/offline/test_auth/test_profile.py::test_reject_non_english` | Member 3 (Kapo) | `non_english_reject_total` |
| INV-CEFR-001 | invariant | design | `src/backend/api/schemas/profile.py` | planned: `test/offline/test_auth/test_profile.py::test_reject_invalid_cefr` | Member 3 (Kapo) | `invalid_cefr_reject_total` |
| INV-SEC-001 | invariant | design | `src/backend/database/vector_client.py` | planned: `test/offline/test_database/test_vector_permissions.py::test_runtime_vector_read_only` | Member 5 (Luming) | `runtime_vector_write_attempt_total` (0) |
| INV-SEC-002 | invariant | design | `src/backend/main.py` | planned: `test/offline/test_api/test_routes.py::test_no_upload_endpoints_exposed` | Member 5 (Luming) | none - structural route introspection |
| INV-PROG-001 | invariant | design | `src/backend/user_progress/service.py` | planned: `test/offline/test_user_progress/test_dashboard.py::test_progress_derived_from_events` | Member 3 (Kapo) | `progress_mismatch_total` (0) |
| INV-CITE-001 | invariant | design | `src/backend/safety_boundary/citation_validator.py` | planned: `test/offline/test_safety_boundary/test_citation_validator.py::test_reject_invalid_citations` | Member 2 (Leon) | `citation_reject_total`, `citation_bypass_total` (0) |
| FR-AUTH-001 | functional | design | `src/backend/auth/router.py` | planned: `test/offline/test_auth/test_auth_flow.py::test_register_login` | Member 3 (Kapo) | `auth_failure_total` |
| FR-PROF-001 | functional | design | `src/backend/auth/router.py` | planned: `test/offline/test_auth/test_profile.py::test_update_profile` | Member 3 (Kapo) | `profile_update_total` |
| FR-CHAT-001 | functional | design | `src/backend/ai_companion/tutor.py` | planned: `test/offline/test_ai_companion/test_tutor.py::test_guided_conversation_flow` | Member 2 (Leon) | `conversation_turn_total` |
| FR-FEED-001 | functional | design | `src/backend/grammar/evaluator.py` | planned: `test/offline/test_grammar/test_evaluator.py::test_writing_feedback_structure` | Member 2 (Leon) | `writing_feedback_total` |
| FR-RAG-001 | functional | design | `src/backend/ai_companion/rag_pipeline.py` | planned: `test/offline/test_ai_companion/test_rag.py::test_grounded_answer_citation` | Member 2 (Leon) | `grounded_answer_total`, `citation_render_total` |
| FR-VOC-001 | functional | design | `src/backend/vocabulary/loader.py` | planned: `test/offline/test_vocabulary/test_loader.py::test_random_selection_with_seed` | Member 3 (Kapo) | `vocabulary_served_total` |
| FR-VOC-002 | functional | design | `src/backend/vocabulary/service.py` | planned: `test/offline/test_vocabulary/test_service.py::test_record_familiarity` | Member 3 (Kapo) | `vocabulary_review_total` |
| FR-DASH-001 | functional | design | `src/backend/user_progress/service.py` | planned: `test/offline/test_user_progress/test_dashboard.py::test_dashboard_metrics_aggregation` | Member 4 (Henry) | `dashboard_projection_errors` |
| FR-CORP-001 | functional | design | `scripts/ingest_content.py` | planned: `test/offline/test_scripts/test_ingestion.py::test_admin_ingest_pipeline` | Member 2 (Leon) | `ingest_report_generated_total` |
| NFR-PERF-001 | performance | design | `src/backend/ai_companion/tutor.py` | planned: `test/live/test_latency.py::test_p95_response_latency` | Member 5 (Luming) | `ai_turn_latency_seconds` p95 |
| NFR-QUAL-001 | quality | design | `src/backend/ai_companion/retrieval_adapter.py` | planned: `test/offline/test_ai_companion/test_retrieval_eval.py::test_recall_at_5` | Member 2 (Leon) | `retrieval_recall_at_5` |
| NFR-QUAL-002 | quality | design | `src/backend/safety_boundary/evaluator.py` | planned: `test/live/test_semantic_eval.py::test_grounded_correctness` | Member 2 (Leon) | `grounded_correctness` (eval run) |
| NFR-QUAL-003 | quality | design | `src/backend/safety_boundary/citation_validator.py` | planned: `test/offline/test_safety_boundary/test_citation_validator.py::test_zero_hallucinated_citations` | Member 2 (Leon) | `citation_validity` (release gate) |
| NFR-QUAL-004 | quality | design | `src/backend/safety_boundary/scope_guard.py` | planned: `test/offline/test_safety_boundary/test_scope_guard.py::test_off_topic_refusal_accuracy` | Member 3 (Kapo) | `off_topic_refusal_accuracy` |
| NFR-SEC-001 | security | design | `src/backend/ai_companion/prompt_assembly.py` | planned: `test/offline/test_safety_boundary/test_prompt_injection.py::test_zero_policy_escapes` | Member 5 (Luming) | `injection_escape_total` (must stay 0) |
| NFR-COST-001 | cost | design | `src/backend/ai_companion/prompt_assembly.py` | planned: `test/offline/test_ai_companion/test_token_budget.py::test_token_cap_enforcement` | Member 2 (Leon) | `prompt_tokens_per_turn` (<= 1,500) |
| NFR-GOV-001 | governance | design | `.github/workflows/ci.yml` | planned: `test/offline/test_governance/test_ci_config.py::test_blocking_gates_declared` | Member 5 (Luming) | none - CI gate evidence only |
| NFR-GOV-002 | governance | design | `.github/workflows/ci.yml` | planned: `test/offline/test_governance/test_ai_log.py::test_log_gate_script` | Member 1 (Adrian) | none - PR gate evidence only |

## Coverage summary

| Dimension | Value | Check |
|---|---|---|
| Rows | 31 | equals SSOT requirement count 31 |
| Must rows with non-empty evidence | 30 / 30 | every Must names a planned test |
| Should rows with non-empty evidence | 1 / 1 | FR-CORP-001 |
| Invariant rows cross-linked to `invariants.md` | 13 / 13 | each `INV-*` appears in the register |
| Rows with a runtime monitor | 29 | 2 governance rows justify `none`; INV-SEC-002 is structural |
| Rows whose state is `tested` | 0 | no implementation at baseline |
| Orphans (requirement without row) | 0 | by construction |
| Dead rows (row without requirement) | 0 | by construction |

## Done-when status at baseline

- [x] Row count equals requirement count; zero orphans both ways (by construction; script pending).
- [x] Every `Must` requirement has a non-empty test/evidence cell (a planned command).
- [ ] Every row whose status is `tested` names an existing test - no row is `tested` yet.
- [ ] `scripts/check_trace.py` exists and fails on an orphan (`DBT-003`).

## Update protocol

1. A new requirement is added to `requirements.yaml` first, then a row is appended here in the same PR.
2. A test landing changes the row from `design` to `implemented`, then `tested` only after it passes in CI; the PR links the run.
3. A requirement becoming `retired` changes the requirement status first; the row stays with `retired` status and its evidence history.
