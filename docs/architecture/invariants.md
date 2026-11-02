# Invariant register - baseline R1

**Status:** declared at baseline. No invariant is `enforced` or `verified` until its failing test exists and passes on the fixed build. The gap is tracked once as `DBT-003` and is not hidden per row.

**Rule:** an invariant is a property that must hold on every execution path, including failure paths. If a row here restates a requirement without naming an enforcer, it is a slogan and must be removed or rewritten.

**Source of truth:** the statement and fit criterion are owned by `docs/req/requirements.yaml`; this file owns enforcement, verification and fallback. This register contains exactly the 13 invariant requirements declared in that registry; any row here without a matching SSOT requirement is not valid.

## Summary

| ID | Statement (one line) | Enforced by | Verified by | Owner |
|---|---|---|---|---|
| INV-SCOPE-001 | Every user message passes scope control before retrieval/LLM | `src/backend/safety_boundary/scope_guard.py` | `test/offline/test_safety_boundary/test_scope_guard.py::test_scope_pipeline_execution_order` | Member 3 (Kapo) |
| INV-SCOPE-002 | Off-topic request gets exact fixed refusal, zero model tokens | `src/backend/safety_boundary/scope_guard.py` | `test/offline/test_safety_boundary/test_scope_guard.py::test_fixed_refusal_response` | Member 3 (Kapo) |
| INV-SCOPE-003 | Rejected request makes zero RAG/LLM calls | `src/backend/api/routers/chat.py` | `test/offline/test_safety_boundary/test_scope_guard.py::test_zero_calls_on_rejection` | Member 3 (Kapo) |
| INV-SCOPE-004 | Uncertain intent gets fixed clarification, no LLM | `src/backend/safety_boundary/scope_guard.py` | `test/offline/test_safety_boundary/test_scope_guard.py::test_uncertain_intent_clarification` | Member 3 (Kapo) |
| INV-SCOPE-005 | Mixed intent blocked, zero retrieval/LLM | `src/backend/safety_boundary/scope_guard.py` | `test/offline/test_safety_boundary/test_scope_guard.py::test_mixed_intent_blocking` | Member 3 (Kapo) |
| INV-SCOPE-006 | Retrieval only when `requires_grounding` is true | `src/backend/ai_companion/retrieval_adapter.py` | `test/offline/test_ai_companion/test_retrieval_conditions.py::test_conditional_retrieval_routing` | Member 2 (Leon) |
| INV-AUTH-001 | No cross-user access; all queries scoped to authenticated user | `src/backend/auth/security.py` | `test/offline/test_auth/test_authorization.py::test_cross_user_isolation` | Member 3 (Kapo) |
| INV-LANG-001 | Only English; `language != 'en'` rejected | `src/backend/api/schemas/profile.py` | `test/offline/test_auth/test_profile.py::test_reject_non_english` | Member 3 (Kapo) |
| INV-CEFR-001 | Only A1/A2/B1/B2 accepted at API boundary | `src/backend/api/schemas/profile.py` | `test/offline/test_auth/test_profile.py::test_reject_invalid_cefr` | Member 3 (Kapo) |
| INV-SEC-001 | Runtime vector DB credentials are read-only | `src/backend/database/vector_client.py` | `test/offline/test_database/test_vector_permissions.py::test_runtime_vector_read_only` | Member 5 (Luming) |
| INV-SEC-002 | Zero file-upload endpoints exposed | `src/backend/main.py` | `test/offline/test_api/test_routes.py::test_no_upload_endpoints_exposed` | Member 5 (Luming) |
| INV-PROG-001 | Dashboard metrics from DB events, never LLM | `src/backend/user_progress/service.py` | `test/offline/test_user_progress/test_dashboard.py::test_progress_derived_from_events` | Member 3 (Kapo) |
| INV-CITE-001 | Citations must match retrieved published chunk IDs, else abstain | `src/backend/safety_boundary/citation_validator.py` | `test/offline/test_safety_boundary/test_citation_validator.py::test_reject_invalid_citations` | Member 2 (Leon) |

---

## INV-SCOPE-001 - Scope pipeline precedes retrieval and model

- **statement:** Every user message must pass through the bounded scope-control pipeline before retrieval or tutor-model invocation.
- **fit_criterion:** 100% of incoming chat requests log an upstream `ScopeResult` prior to any vector store or LLM client call.
- **enforced_by:** `scope_guard.py` runs first in the chat router; no retrieval/LLM client is reachable until a `ScopeResult` is produced.
- **verification:** ordering test asserts a `ScopeResult` is recorded before any mocked vector/LLM call. `test/offline/test_safety_boundary/test_scope_guard.py::test_scope_pipeline_execution_order`
- **fallback:** reject the turn before any downstream call; return a fixed clarification/refusal; log a CRITICAL audit event.
- **status:** declared
- **source:** `INV-SCOPE-001` in `docs/req/requirements.yaml`

## INV-SCOPE-002 - Fixed refusal for off-topic requests

- **statement:** A user request determined to be unrelated to language learning must receive the approved deterministic fixed refusal string.
- **fit_criterion:** Returns exact string `"I'm sorry, but I can only help with language-learning questions."` with HTTP 200 and zero model-generated tokens.
- **enforced_by:** `scope_guard.py` returns the constant refusal before model invocation.
- **verification:** `test/offline/test_safety_boundary/test_scope_guard.py::test_fixed_refusal_response`
- **fallback:** return the fixed refusal string; no model call; no state mutation.
- **status:** declared
- **source:** `INV-SCOPE-002` in `docs/req/requirements.yaml`

## INV-SCOPE-003 - Zero calls on rejection

- **statement:** A deterministically rejected request must make exactly zero RAG vector searches and zero tutor LLM calls.
- **fit_criterion:** Vector search mock call count == 0 and LLM API client call count == 0 for all rejected test cases.
- **enforced_by:** `chat.py` router checks the scope verdict and short-circuits before retrieval/LLM.
- **verification:** `test/offline/test_safety_boundary/test_scope_guard.py::test_zero_calls_on_rejection`
- **fallback:** return the scope refusal/clarification; assert zero downstream calls; log a CRITICAL audit event.
- **status:** declared
- **source:** `INV-SCOPE-003` in `docs/req/requirements.yaml`

## INV-SCOPE-004 - Uncertain intent clarification

- **statement:** An uncertain intent request must return the approved fixed clarification response and must not bypass scope control.
- **fit_criterion:** Ambiguous user inputs deterministically yield `status='uncertain'`, zero external LLM calls, and a static clarification prompt.
- **enforced_by:** `scope_guard.py` classifies ambiguous input as `uncertain` and returns the fixed clarification.
- **verification:** `test/offline/test_safety_boundary/test_scope_guard.py::test_uncertain_intent_clarification`
- **fallback:** return the static clarification prompt; no model call.
- **status:** declared
- **source:** `INV-SCOPE-004` in `docs/req/requirements.yaml`

## INV-SCOPE-005 - Mixed-intent blocking

- **statement:** A mixed-intent request must not silently execute an unsupported part and must return a fixed resubmission clarification.
- **fit_criterion:** Inputs containing partial off-topic actions yield `status='mixed'` and zero retrieval or tutor calls.
- **enforced_by:** `scope_guard.py` classifies as `mixed` and blocks all downstream execution.
- **verification:** `test/offline/test_safety_boundary/test_scope_guard.py::test_mixed_intent_blocking`
- **fallback:** return the fixed resubmission clarification; no model call; no state mutation.
- **status:** declared
- **source:** `INV-SCOPE-005` in `docs/req/requirements.yaml`

## INV-SCOPE-006 - Conditional retrieval only

- **statement:** Retrieval from the vector database must be conditional and executed only when `requires_grounding` is true.
- **fit_criterion:** Zero vector search calls for ungrounded conversation, writing feedback, vocabulary JSON lookup, or rejected states.
- **enforced_by:** `retrieval_adapter.py` gates retrieval on the `requires_grounding` flag.
- **verification:** `test/offline/test_ai_companion/test_retrieval_conditions.py::test_conditional_retrieval_routing`
- **fallback:** skip retrieval; answer without citations; record the routing decision.
- **status:** declared
- **source:** `INV-SCOPE-006` in `docs/req/requirements.yaml`

## INV-AUTH-001 - Cross-user isolation

- **statement:** Cross-user data access is strictly forbidden; all session, progress, and vocabulary queries must be scoped to the authenticated user ID.
- **fit_criterion:** Access attempts using another user's session ID or user ID yield HTTP 403/404 with 0 record disclosures and 0 state mutations.
- **enforced_by:** `auth/security.py` scopes every record query to the authenticated user ID.
- **verification:** `test/offline/test_auth/test_authorization.py::test_cross_user_isolation`
- **fallback:** return 404 with an empty body; append a SECURITY event with resource type only; no mutation.
- **status:** declared
- **source:** `INV-AUTH-001` in `docs/req/requirements.yaml`

## INV-LANG-001 - English only

- **statement:** The application supports only the English language; all registration and profile requests with `language != 'en'` must be rejected.
- **fit_criterion:** Payloads with `language != 'en'` fail with HTTP 422 Unprocessable Entity.
- **enforced_by:** `api/schemas/profile.py` validates the language field.
- **verification:** `test/offline/test_auth/test_profile.py::test_reject_non_english`
- **fallback:** return 422 with a field error; no persistence.
- **status:** declared
- **source:** `INV-LANG-001` in `docs/req/requirements.yaml`

## INV-CEFR-001 - Canonical CEFR levels only

- **statement:** The system accepts only canonical CEFR levels A1, A2, B1, and B2; any other level values must be rejected at the API boundary.
- **fit_criterion:** Payloads containing levels outside `['A1', 'A2', 'B1', 'B2']` fail schema validation with HTTP 422.
- **enforced_by:** `api/schemas/profile.py` enumerates the allowed levels.
- **verification:** `test/offline/test_auth/test_profile.py::test_reject_invalid_cefr`
- **fallback:** return 422 with a field error; no persistence.
- **status:** declared
- **source:** `INV-CEFR-001` in `docs/req/requirements.yaml`

## INV-SEC-001 - Read-only vector credentials

- **statement:** The runtime application service must use read-only vector database credentials and cannot execute insert, update, or delete commands.
- **fit_criterion:** Direct SQL/vector write operations executed via the application DB pool raise a permission-denied exception.
- **enforced_by:** `database/vector_client.py` uses a read-only role; writes raise permission-denied.
- **verification:** `test/offline/test_database/test_vector_permissions.py::test_runtime_vector_read_only`
- **fallback:** the write fails with permission-denied; no data changes; log a SECURITY event.
- **status:** declared
- **source:** `INV-SEC-001` in `docs/req/requirements.yaml`

## INV-SEC-002 - No upload endpoints

- **statement:** The web application and backend API must expose zero user file upload endpoints.
- **fit_criterion:** API router introspection confirms 0 registered routes accepting `multipart/form-data` or file payloads.
- **enforced_by:** `main.py` registers no upload routes.
- **verification:** `test/offline/test_api/test_routes.py::test_no_upload_endpoints_exposed`
- **fallback:** unroutable; no upload path exists.
- **status:** declared
- **source:** `INV-SEC-002` in `docs/req/requirements.yaml`

## INV-PROG-001 - Progress derived from events

- **statement:** Dashboard progress metrics must be aggregated deterministically from verified database events and never from LLM output.
- **fit_criterion:** Progress response counts exactly match SQL `COUNT(*)` queries from the `learning_events` table.
- **enforced_by:** `user_progress/service.py` reads aggregate counts directly; no model narrative path.
- **verification:** `test/offline/test_user_progress/test_dashboard.py::test_progress_derived_from_events`
- **fallback:** recompute directly from events; if parity fails, return 503 and hide numeric cards; log a CRITICAL event.
- **status:** declared
- **source:** `INV-PROG-001` in `docs/req/requirements.yaml`

## INV-CITE-001 - Citation provenance

- **statement:** All displayed lesson citations must match retrieved, published chunk IDs; invalid or missing source IDs must trigger safe abstention.
- **fit_criterion:** Tutor responses with unverified citation IDs are discarded; response falls back to an insufficient-evidence disclosure.
- **enforced_by:** `citation_validator.py` checks every source ID against the retrieved published set.
- **verification:** `test/offline/test_safety_boundary/test_citation_validator.py::test_reject_invalid_citations`
- **fallback:** discard the entire answer; return an abstention with the limitation phrase; log `validation_result=rejected_citation` at CRITICAL.
- **status:** declared
- **source:** `INV-CITE-001` in `docs/req/requirements.yaml`

---

## Verification protocol

Each invariant's test must satisfy three conditions before the status can move to `verified`:

1. **It fails on the broken build.** The evidence is a logbook row with the failing assertion, not a reviewer's statement.
2. **It exercises the violation path,** not a happy path with an assertion attached. A test that passes on a build where the enforcement is bypassed proves nothing.
3. **It names the invariant and requirement in its docstring,** e.g. `"""INV-SCOPE-001: scope result must precede any downstream call."""`.

## Done-when status at baseline

- [ ] Each invariant has a test that fails when the invariant is violated (`DBT-003`).
- [ ] Each fallback is an action the code can take without a human (designed; not implemented).
- [x] Each `enforced_by` names exactly one module matching an SSOT `enforcing_component` path.
- [x] The register contains exactly the 13 SSOT invariant requirements; no extra or missing rows.
