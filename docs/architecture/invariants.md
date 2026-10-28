# Invariant register - baseline R1 (round 1)

**Status:** declared at baseline, 2026-10-27. No invariant is `enforced` or `verified` until its failing test exists and passes on the fixed build. The gap is tracked once as `DBT-003` and is not hidden per row.

**Rule:** an invariant is a property that must hold on every execution path, including failure paths. If a row here restates a requirement without naming an enforcer, it is a slogan and must be removed or rewritten.

**Source of truth:** the statement and fit criterion are owned by `docs/req/requirements.yaml`; this file owns enforcement, verification and fallback.

## Summary

| ID | Statement (one line) | Enforced by | Verified by | Round |
|---|---|---|---|---|
| INV-001 | No unvalidated model output is displayed or persisted | `ResponseValidator.validate_output()` | `test_inv_001_no_unvalidated_output.py` | 1 |
| INV-002 | No citation outside the retrieved published set is displayed | `ResponseValidator.validate_citations()` | `test_inv_002_citation_provenance.py` | 1 |
| INV-003 | No learner reads or writes another learner's record | `OwnershipGuard.authorize()` | `test_inv_003_cross_user_isolation.py` | 1 |
| INV-004 | No client-supplied quiz score is accepted | `AssessmentService.score_attempt()` | `test_inv_004_backend_scoring.py` | 1 |
| INV-005 | Every displayed total equals the stored event aggregate | `ProgressLedger.project_progress()` | `test_inv_005_progress_parity.py` | 1 |
| INV-006 | No failure path skips validation or authorization | `TutorPipeline.handle_turn()` | `test_inv_006_no_safety_bypass.py` | 1 |
| INV-007 | Retrieved text cannot change policy, tools or authorization | `PromptAssembler.assemble()` | `test_inv_007_retrieved_text_is_data.py` | 1 |
| INV-008 | Only active published content is served | `RetrievalService.search()` | `test_inv_008_published_only.py` | 1 |
| INV-009 | Learner writing never enters the shared corpus | `ContentPublisher.ingest()` | `test_inv_009_privacy_boundary.py` | 1 |
| INV-010 | Audit records never contain raw learner text | `ObservabilityStore.append_turn_event()` | `test_inv_010_redaction.py` | 1 |
| INV-011 | Memory cannot influence scores, progress or authorization | `SessionSummaryStore.get()` | `test_inv_011_summary_isolation.py` | 1 |

---

## INV-001 - No unvalidated model output

- **statement:** No model-generated text SHALL be displayed to a learner or persisted as a learning record unless it carries a successful `ResponseValidator` verdict.
- **source:** `REQ-LANG-INV-001`
- **enforced_by:** `ResponseValidator.validate_output()` (the single authoritative gate; imported only by `TutorPipeline`)
- **verification:** negative test injects a bypass path that returns model text without a verdict; the test asserts the response is not rendered and the record count is unchanged. Boundary suite includes malformed schema, oversized output and a valid control. `test/offline/invariants/test_inv_001_no_unvalidated_output.py::test_no_unvalidated_output` fails on the broken build (V2).
- **fallback:** discard the output, return `SAFE_FALLBACK` with a retry message, append a CRITICAL audit event, and leave the learner record unchanged.
- **status:** declared
- **round:** 1
- **adr:** ADR-005 §Decision, §Rejection codes; ADR-001 §Decision

## INV-002 - Citation provenance

- **statement:** The system SHALL NOT display a citation whose `source_id` is absent from the published chunks retrieved for that turn.
- **source:** `REQ-LANG-INV-002`
- **enforced_by:** `ResponseValidator.validate_citations()` (subset check against `EvidenceSet.published_ids`)
- **verification:** tests for unknown id, retired id, id from another level, and a valid id; each negative case must produce no citation and an abstention. `test/offline/invariants/test_inv_002_citation_provenance.py`
- **fallback:** discard the entire answer, return an abstention with the limitation phrase, log `validation_result=rejected_citation` at CRITICAL with the offending id.
- **status:** declared
- **round:** 1
- **adr:** ADR-005 §Response contracts; ADR-007 §Decision

## INV-003 - Cross-user isolation

- **statement:** A learner SHALL NOT read, update or delete another learner's record by any request path.
- **source:** `REQ-LANG-SEC-002`
- **enforced_by:** `OwnershipGuard.authorize()` (called by every repository-backed service; no direct table access from the gateway)
- **verification:** 20 probes across sessions, messages, writing, vocabulary, quizzes and dashboard; each returns 404 with no body and writes no mutation. `test/offline/invariants/test_inv_003_cross_user_isolation.py`
- **fallback:** return 404 with an empty body, append a SECURITY event with the resource type (not content), and alert the operator after 5 denials in 10 minutes.
- **status:** declared
- **round:** 1
- **adr:** ADR-001 §Boundaries; ADR-010 §Roles

## INV-004 - Backend-only scoring

- **statement:** A quiz score SHALL be computed only by server-side code; a client-supplied score SHALL be ignored and never stored.
- **source:** `REQ-LANG-INV-004`
- **enforced_by:** `AssessmentService.score_attempt()` (loads the stored key; ignores `score` in the request model)
- **verification:** 12 forged-score attempts, including a valid answer with a wrong claimed score; stored score equals the deterministic result in every case. `test/offline/invariants/test_inv_004_backend_scoring.py`
- **fallback:** ignore the field, recompute from the key, append a CRITICAL audit event with `request_id`, and return the true score.
- **status:** declared
- **round:** 1
- **adr:** ADR-008 §Scoring rules; ADR-005 §Rejection codes

## INV-005 - Event-sourced totals

- **statement:** Every displayed progress total SHALL equal the aggregate of the learner's stored learning events for that period.
- **source:** `REQ-LANG-INV-005`
- **enforced_by:** `ProgressLedger.project_progress()` (reads events; an optional cache is parity-checked in the same request)
- **verification:** a 50-event fixture plus a 200-request randomised parity run; the displayed total and the direct event aggregate are compared; any mismatch fails. `test/offline/invariants/test_inv_005_progress_parity.py`
- **fallback:** recompute directly from events; if parity still fails, return 503 for the dashboard with a retry message, hide the numeric cards, and append a CRITICAL event.
- **status:** declared
- **round:** 1
- **adr:** ADR-008 §Event model; ADR-001 §Authority

## INV-006 - No safety bypass

- **statement:** No failure path SHALL skip `ResponseValidator` or `OwnershipGuard` when producing or persisting a turn.
- **source:** `REQ-LANG-INV-006`
- **enforced_by:** `TutorPipeline.handle_turn()` (fail-closed orchestration; the degradation route never returns raw model text)
- **verification:** 12 fault injections across model timeout, malformed output, retrieval outage, database timeout and summary failure; each asserts zero calls to persistence with unvalidated text and zero display. `test/offline/invariants/test_inv_006_no_safety_bypass.py`
- **fallback:** fail closed: no display, no persistence, `SAFE_FALLBACK` message, CRITICAL audit event, increment `safety_bypass_total` (must stay 0).
- **status:** declared
- **round:** 1
- **adr:** ADR-001 §Decision; ADR-005 §Decision

## INV-007 - Retrieved text is data

- **statement:** Retrieved passages SHALL be treated as untrusted data and SHALL NOT alter system policy, tool privileges, or authorization.
- **source:** `REQ-LANG-SEC-001`
- **enforced_by:** `PromptAssembler.assemble()` (delimited untrusted block; restated constraints after evidence; no tool schema in the prompt)
- **verification:** 24 adversarial cases across injection, role-play, tool-request and data-exfiltration families; zero policy escapes and zero privilege changes. `test/offline/invariants/test_inv_007_retrieved_text_is_data.py`
- **fallback:** quarantine the flagged chunk, remove it from evidence, re-retrieve once; if no safe evidence remains, abstain. Append a SECURITY event; never execute a tool request from content.
- **status:** declared
- **round:** 1
- **adr:** ADR-005 §Decision; ADR-006 §Assembly pipeline

## INV-008 - Published-only serving

- **statement:** Only chunks belonging to the active published version of a source SHALL be served to retrieval, and a retired version SHALL be excluded before the next query.
- **source:** `REQ-LANG-GOV-001`
- **enforced_by:** `RetrievalService.search()` (joins active versions and filters published/language/level/topic before ranking)
- **verification:** 64 replay cases plus 8 retirement-race cases; zero unpublished or retired chunks in any evidence set; a chunk retired mid-turn is rejected by the validator. `test/offline/invariants/test_inv_008_published_only.py`
- **fallback:** exclude the chunk, re-retrieve once; if no active evidence remains, abstain; append a CRITICAL event with the version id.
- **status:** declared
- **round:** 1
- **adr:** ADR-007 §Publication model; ADR-007 §Ingestion and activation flow

## INV-009 - Learner writing stays out of the corpus

- **statement:** Raw learner writing SHALL NOT enter the shared curriculum corpus, the vector index, or a content version.
- **source:** `REQ-LANG-SEC-004`
- **enforced_by:** `ContentPublisher.ingest()` (accepts only manifest-declared licensed sources; rejects files under learner paths; no writer from learner tables)
- **verification:** a test attempts to ingest a writing submission path and a chunk containing a learner email; both are rejected; a scan of the manifest and index metadata finds zero learner-text markers. `test/offline/invariants/test_inv_009_privacy_boundary.py`
- **fallback:** reject the ingest, quarantine the source, leave the active version untouched, append a SECURITY event, and block the publish until a human clears it.
- **status:** declared
- **round:** 1
- **adr:** ADR-007 §Decision; ADR-009 §Store inventory

## INV-010 - Audit records are redacted

- **statement:** Operational and audit records SHALL NOT contain raw learner writing, email, display name or provider keys.
- **source:** `REQ-LANG-SEC-004`
- **enforced_by:** `ObservabilityStore.append_turn_event()` (writes a field allowlist; hashes user ref and text; rejects unknown fields)
- **verification:** 100 sampled events, including a deliberately injected raw-text field; the raw value must be absent; a redaction fixture covers email, Chinese text and a key-like string. `test/offline/invariants/test_inv_010_redaction.py`
- **fallback:** drop the offending field, write only the allowlisted fields, append a security event to a separate sink without the value, and alert after any redaction failure.
- **status:** declared
- **round:** 1
- **adr:** ADR-009 §Privacy rules; ADR-001 §Observability

## INV-011 - Memory cannot influence decisions

- **statement:** No session summary or vocabulary history SHALL influence quiz scoring, progress totals, authorization or content eligibility.
- **source:** `REQ-LANG-FR-009`
- **enforced_by:** `SessionSummaryStore.get()` (owner-scoped read; import contract forbids `AssessmentService`, `ProgressLedger`, `OwnershipGuard`, `RequestAuthenticator` and `ContentPublisher` from importing it)
- **verification:** import-linter contract plus a behavioural test that changes a summary and asserts scores, totals and authorization are unchanged. `test/offline/invariants/test_inv_011_summary_isolation.py`
- **fallback:** strip the summary from the prompt, continue with recent history only, record a CRITICAL event, and run the isolation test before the next release.
- **status:** declared
- **round:** 1
- **adr:** ADR-009 §Decision; ADR-006 §Assembly pipeline

---

## Verification protocol (V2)

Each invariant's test must satisfy three conditions before the status can move to `verified`:

1. **It fails on the broken build.** The evidence is a logbook row with the failing assertion, not a reviewer's statement.
2. **It exercises the violation path,** not a happy path with an assertion attached. A test that passes on a build where the validator is bypassed proves nothing.
3. **It names the invariant and requirement in its docstring,** e.g. `"""INV-002 / REQ-LANG-INV-002: unknown source id must not render."""`; `test/structural/test_docstring_trace.py` checks the tag.

## Done-when status at baseline

- [ ] Each invariant has a test that fails when the invariant is violated (planned; `DBT-003`).
- [ ] Each fallback is an action the code can take without a human (designed; not implemented).
- [x] Each `enforced_by` names exactly one module from the blueprint component table.
- [x] Round-1 rows only; any round-2 invariant is appended, never merged into an existing row.
- [x] Every row cites exactly one source requirement and at least one ADR section.
