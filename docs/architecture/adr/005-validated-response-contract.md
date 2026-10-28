# ADR-005: Adopt a server-validated structured response contract for all tutor output

- **Status:** Accepted
- **Date:** 2026-10-27
- **Supersedes:** -
- **Decision owner:** Member 2 (AI & RAG) with Member 3 (Backend & Data)
- **Related requirements:** REQ-LANG-ARCH-001, REQ-LANG-INV-001, REQ-LANG-INV-002, REQ-LANG-SEC-001, REQ-LANG-FR-003, REQ-LANG-FR-004, REQ-LANG-FR-007, REQ-LANG-NFR-002, REQ-LANG-NFR-006, REQ-LANG-GOV-002
- **Related artifacts:** ADR-001, ADR-006, `docs/architecture/invariants.md` INV-001/002/007, `runtime-policy-catalog.md` RP-001/RP-003/RP-004, `structural-constraints.md` S4, `mcp-tool-manifest.md`
- **Review triggers:** `citation_reject_total > 0`; `schema_reject_total / turns > 5%` in a rolling week; repair-attempt success `< 50%`; `tutor_response_p95_seconds > 12` for 3 days; the provider changes or removes structured-output mode; a new task type is proposed without a contract; any change to `ResponseValidator` rules.

## Context

The tutor produces four kinds of output: a conversational reply, a grounded lesson answer with citations, writing feedback, and a quiz draft. Each has a different structure and a different failure cost.

A free-form response is the easiest to generate and the hardest to govern. It gives the validator nothing to check except length; a plausible sentence with an invented citation is indistinguishable from a grounded one. The lecture's warning applies directly: a rule that cannot be checked is a rule the agent will invent a behaviour for.

The forces:

- CL-AUTHORITY requires that no model text reach a learner or a record without a deterministic verdict.
- CL-GROUNDING requires that every citation resolve to a retrieved published chunk.
- CL-RESILIENCE requires that a malformed response become a safe fallback, not an exception swallowed by the pipeline.
- CL-COST and latency forbid an unbounded repair loop or a second model critic in R1.

## Decision

Require every model call to return a task-specific JSON object, and accept it only through `ResponseValidator.validate(output, evidence) -> Verdict`, a pure function that checks schema, provenance, length, markup and abstention consistency before display or persistence.

A failed validation gets **one** repair attempt with the same evidence set and temperature 0 only when the failure is repairable (`schema_invalid`, `unsafe_markup`, `over_length`). Citation, authority and tool-request failures are not repairable in the same turn: they discard the output and return a safe fallback.

## Rationale

- A typed contract gives the validator concrete predicates. "Every `source_id` is in `evidence.published_ids`" is a one-line check; "the answer seems grounded" is not.
- Rejecting unknown fields prevents a model from smuggling a `tool`, `role`, `system` or `url` field into a response and hoping a later component honours it.
- One bounded repair handles the common formatting failure without turning into a retry loop that consumes the latency budget.
- Keeping citation failures non-repairable is deliberate: if the model invents a source once, allowing it to retry in the same turn teaches it to invent a different one. The safe fallback is the honest outcome.
- The client never contributes to validation. Source titles and sections are rendered from server-held metadata by ID, never from model-supplied text.

## Response contracts

### Common envelope

| Field | Type | Required | Validation |
|---|---|---|---|
| `task` | enum `conversation` `lesson_help` `writing_feedback` `quiz_draft` | yes | must equal the requested task |
| `abstained` | boolean | yes | if true, `source_ids` must be empty and `answer` must contain the limitation phrase |
| `source_ids` | array of strings, max 5 | yes | every id must be in `evidence.published_ids`; no duplicates |
| `answer` | string, max 1,200 chars | yes | markdown allowlist (bold, italics, lists, inline code); no raw HTML |
| `follow_up` | string, max 300 chars | no | no question mark requirement; must not introduce a new fact |
| `tips` | array of strings, max 2 x 200 chars | no | no citations may appear only in tips |
| `validation_id` | assigned by server | output | not model-controlled |

### Task-specific additions

| Task | Additional fields | Rule |
|---|---|---|
| `conversation` | none | `source_ids` may be empty; no citation is displayed |
| `lesson_help` | none | at least one `source_id` unless `abstained` is true |
| `writing_feedback` | `suggested_text` (max 1,500), `explanation` (max 800), `examples` (max 2 x 300) | `suggested_text` never replaces the stored original; it is a proposal |
| `quiz_draft` | `items` (3-5), each with `question` (max 300), `options` (3-4 x 120), `correct_index`, `explanation` (max 500), `source_ids` | the key is stripped before the client sees the item; malformed item rejects the whole quiz |

### Rejection codes

| Code | Trigger | Repairable in-turn? | Action |
|---|---|---|---|
| `schema_invalid` | missing/wrong field, unknown field, wrong enum | yes, once | repair prompt with the schema and the error path |
| `over_length` | any cap exceeded | yes, once | repair prompt with the cap |
| `unsafe_markup` | script/HTML/URL not allowed by policy | yes, once | repair prompt with the allowlist |
| `citation_unknown` | `source_id` not in retrieved set | no | discard; abstain; log CRITICAL |
| `citation_unpublished` | source id exists but is retired/unpublished | no | discard; abstain; security event |
| `abstention_inconsistent` | `abstained=true` with citations, or limitation missing | no | discard; safe fallback |
| `tool_request` | any tool/function/role field present | no | discard; security event |
| `quiz_key_invalid` | missing/ambiguous key or duplicate options | no | discard; regenerate next turn |

## Responsibility map

| Element | Responsibility | Implemented in |
|---|---|---|
| `TutorPipeline` | Request the task contract, pass evidence, stop on a failed verdict | `src/tutor_pipeline.py` |
| `ModelGateway` | Enforce structured output, timeout, one repair call, token cap | `src/model_gateway.py` |
| `ResponseValidator` | Pure schema, provenance, length, markup and abstention checks | `src/response_validator.py` |
| `DegradationController` | Map a non-repairable failure to `SAFE_FALLBACK` or abstention | `src/degradation_controller.py` |
| `ObservabilityStore` | Record rejection code, repair count and validation id | `src/observability_store.py` |

## Quality attribute tradeoffs

| Attribute | Tactic | Buys | Costs | Metric that would invalidate |
|---|---|---|---|---|
| Safety | Server-side typed validation, unknown fields rejected | Provable no-bypass path | Occasional rejection of otherwise good prose | `validation_bypass_count > 0` |
| Grounding | Citation IDs checked against retrieved published set | No fabricated authority | Answers without a retrieved source must abstain | `citation_validity < 100%` |
| Resilience | One repair attempt, then fallback | Formatting noise is absorbed | A second failure costs one extra call | `validation_reject_rate > 5%` |
| Latency | Repair only for repairable errors; 25 s provider timeout | Bounded turn time | Some turns end in a retry message | `p95 > 12 s` |
| Cost | One repair max; output token cap 700 | Predictable spend | Shorter explanations | `session_cost_usd > 0.04` |
| Maintainability | One contract per task, versioned with the prompt | Changes are reviewable | Adding a task requires a schema and tests | schema version bump without migration |

## Alternatives considered

| Option | Failed criterion | Evidence |
|---|---|---|
| Free-form prose with post-hoc regex and keyword checks | Invariant protection: a regex cannot prove that a quoted lesson exists in the retrieved set | `evaluation-table.md` C1 explanation-isolation rule; `INV-002` |
| Model self-critique ("check your own citations") | Authority separation: the same model is not an independent gate, and a self-check can rationalise an invented source | `INV-001`; no authoritative verifier in the path |
| Client-side JSON schema validation | Isolation/authority: the client is untrusted and can be bypassed; it also cannot know the retrieved set | `REQ-LANG-ARCH-001`, `REQ-LANG-SEC-002` |
| Provider JSON mode without server checks | Grounding: schema-valid output can still contain an unpublished or invented `source_id` | `INV-002`; RP-004 |
| Two-model critic in R1 | Cost and latency: doubles model spend and adds a second non-deterministic judge without a deterministic gate | `COST-002`, `NFR-004`; deferred to round 2 only with an ADR |

## Consequences

**Benefits**

- Every safety claim maps to a named rejection code and a test.
- Unknown fields are rejected, which closes the "model invents a tool field" class of attack.
- The validator is a pure function, so it can be exhaustively tested offline with fixtures and fuzzing.
- Citation rendering uses server metadata, so a model cannot fabricate a URL or a title.

**Costs**

- More prompt engineering: the schema occupies ~300 tokens on every call.
- More rejection paths to test; `schema_reject_total` becomes an operational metric.
- Legitimate answers can be lost to a strict length or markup cap; the repair attempt absorbs most, not all.
- The quiz draft schema complicates prompt design; a malformed item rejects the whole quiz.

## Review triggers

| Trigger | Threshold | Action |
|---|---|---|
| Citation bypass at runtime | any occurrence | Open a post-incident ADR; add a failing test before the fix |
| Schema rejection rate | > 5% of turns in a rolling week | Review prompt/schema; open an ADR for a repair-prompt change |
| Repair success rate | < 50% | Inspect rejection codes; if citation-driven, do not relax the rule |
| Provider structured-output change | any breaking change | New provider ADR; rerun EVAL-1.0.0 |
| New task type | proposed | Add a contract section, validator rules, tests and eval cases before code |
| Latency | p95 > 12 s for 3 days | Reduce repair or context budget; REVIEW |

## Change log

| Date | Change | Evidence |
|---|---|---|
| 2026-10-27 | Initial contract accepted at baseline R1 | `evaluation-logbook.md` 2026-10-27; `trace-matrix.md` rows for REQ-LANG-ARCH-001 and REQ-LANG-INV-002 |
