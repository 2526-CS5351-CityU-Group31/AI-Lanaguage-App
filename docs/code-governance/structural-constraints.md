# Structural constraints - baseline R1

**Purpose:** state how code must be organised, extended and bounded, so the rules apply regardless of which element is being built.
**Consumers:** Build agent (every file it writes), Tier-1 fitness functions, reviewers.
**Owner:** Member 3 (Backend & Data); enforcement co-owned by Member 5.
**Status:** declared. The mechanisms below are the required checks; their implementation is tracked by `DBT-002`/`DBT-003`.

## 1. Module organisation (S1)

**Rule:** each module named in an SSOT `enforcing_component` maps to exactly one file; one module has one primary class. The module layout is nested under `src/backend/` and mirrors the SSOT package structure. A module that holds two responsibilities forces unrelated changes to touch it and makes the import boundary unprovable.

| Element | Module | Primary class | Zone | Enforces (reqs) |
|---|---|---|---|---|
| ScopeGuard | `src/backend/safety_boundary/scope_guard.py` | `ScopeGuard` | authoritative | INV-SCOPE-001/002/004/005, NFR-QUAL-004 |
| CitationValidator | `src/backend/safety_boundary/citation_validator.py` | `CitationValidator` | authoritative | INV-CITE-001, NFR-QUAL-003 |
| SafetyEvaluator | `src/backend/safety_boundary/evaluator.py` | `SafetyEvaluator` | authoritative | NFR-QUAL-002 |
| RetrievalAdapter | `src/backend/ai_companion/retrieval_adapter.py` | `RetrievalAdapter` | advisory | INV-SCOPE-006, NFR-QUAL-001 |
| RagPipeline | `src/backend/ai_companion/rag_pipeline.py` | `RagPipeline` | advisory | FR-RAG-001 |
| Tutor | `src/backend/ai_companion/tutor.py` | `Tutor` | advisory | FR-CHAT-001, NFR-PERF-001 |
| PromptAssembly | `src/backend/ai_companion/prompt_assembly.py` | `PromptAssembler` | advisory | NFR-SEC-001, NFR-COST-001 |
| ChatRouter | `src/backend/api/routers/chat.py` | `ChatRouter` | boundary | INV-SCOPE-003 |
| ProfileSchema | `src/backend/api/schemas/profile.py` | `ProfileSchema` | boundary | INV-LANG-001, INV-CEFR-001 |
| AuthRouter | `src/backend/auth/router.py` | `AuthRouter` | service | FR-AUTH-001, FR-PROF-001 |
| AuthSecurity | `src/backend/auth/security.py` | `AuthSecurity` | authoritative | INV-AUTH-001 |
| VectorClient | `src/backend/database/vector_client.py` | `VectorClient` | data | INV-SEC-001 |
| GrammarEvaluator | `src/backend/grammar/evaluator.py` | `GrammarEvaluator` | service | FR-FEED-001 |
| AppEntry | `src/backend/main.py` | `AppEntry` | composition root | INV-SEC-002 |
| ProgressService | `src/backend/user_progress/service.py` | `ProgressService` | service | INV-PROG-001, FR-DASH-001 |
| VocabularyLoader | `src/backend/vocabulary/loader.py` | `VocabularyLoader` | data | FR-VOC-001 |
| VocabularyService | `src/backend/vocabulary/service.py` | `VocabularyService` | service | FR-VOC-002 |
| IngestScript | `scripts/ingest_content.py` | `IngestPipeline` | tool | FR-CORP-001 |

**Zones:**
- **authoritative** (`safety_boundary/`, `auth/security.py`): can veto model output or authorize records; never depend on live LLM calls; stdlib + vetted deterministic libs only.
- **advisory** (`ai_companion/`): may propose text/citations/feedback; may not write learner state.
- **boundary** (`api/`): HTTP typing, schema validation, request/response mapping.
- **service** / **data** / **composition root** as implied by name.

**S1 enforcement:** `pytest-archon` enforces one primary class per module and naming; `test/structural/test_module_map.py` compares the AST module list to this table. A new module without a row fails Tier 1.

## 2. Extension, never replacement (S2)

**Rule:** a new design round extends the baseline. Applied migrations and published content versions are immutable; a revision build carries a delta spec with `OBSOLETED / ADDED / MODIFIED / FROZEN` lists. An `OBSOLETED` element must have zero imports after the round (grep/AST check).

| Frozen path | Zero-diff check |
|---|---|
| `docs/req/requirements.yaml` | baseline delta only |
| `docs/req/req-schema.json`, `docs/req/prd.yaml` | baseline delta only |
| `docs/architecture/adr/001,005-010` | append-only; supersede with a new ADR |
| `architecture-blueprint.md` | ADR + human approval |
| Applied `migrations/*.sql` | new migration only |
| Published `content/` versions | retire, never edit |
| `.opencode/rules.md`, `.opencode/permissions.jsonc`, `.agent/rules.md`, `.github/workflows/ci.yml` | human-only writes |

## 3. ADR and invariant traceability in code (S3)

**Rule:** every module states which element it implements and which ADR governs it; every non-trivial public function names the ADR section and the invariant/requirement it implements.

Module docstring format:

```python
"""ScopeGuard - deterministic intent gate before retrieval/model.

Element: ScopeGuard
Implements: ADR-001 §Decision; INV-SCOPE-001, INV-SCOPE-002, INV-SCOPE-004, INV-SCOPE-005
"""
```

Function docstring format:

```python
def classify(message: str) -> ScopeResult:
    """Classify intent and short-circuit off-topic turns.

    Implements: ADR-005 §Rejection codes; INV-SCOPE-002
    """
```

- The tag pattern is `ADR-[0-9]{3}` and `INV-[A-Z]+-[0-9]{3}` (or `FR-`/`NFR-`); `test/structural/test_docstring_trace.py` parses the AST and fails on a missing tag.
- A docstring that names a non-existent ADR or requirement is a failure, not a warning.

## 4. Authority and import boundaries (S4)

| Contract | Rule | Failure signal |
|---|---|---|
| C1 - single validator | `citation_validator` may be imported only by `ai_companion/rag_pipeline` (assessment/pipeline) and tests | any other importer |
| C2 - scope gate first | `scope_guard` may be imported only by `api/routers/chat` and tests | a path that reaches retrieval/model without it |
| C3 - advisory no-write | `ai_companion/**` must not import `database/**` or any write service | any db/domain write import |
| C4 - safety stdlib-only | `safety_boundary/**` must not import `ai_companion/**` or any LLM client | any model/advisory import |
| C5 - data adapter | `database/vector_client` may be imported only by `retrieval_adapter` and ingestion | any other importer |
| C6 - composition root | `main.py` wires routers/app; routers import no other router | cross-router import |
| C7 - config boundary | only the config module references `os.environ`/`getenv`/`dotenv` | any other reference |

A circuit breaker, rate limiter or retry wrapper may wrap the advisory zone, **never** the deterministic safety gate.

## 5. Configuration boundary (S5)

- A single config module is the only one that reads the environment; every other module receives a frozen config object.
- `grep -rn "os\.environ\|os\.getenv\|load_dotenv" src --include='*.py' | grep -v 'config.py:'` must produce no output.
- A module that constructs its own config or reads an env var after startup fails Tier 1.

## 6. Single-writer stores (S6)

| Store | Sole writer | Allowed readers |
|---|---|---|
| `users`, `sessions` | `auth/security.py` | `auth/router.py` (own) |
| `user_vocabulary` | `vocabulary/service.py` | owner reads |
| `learning_events` | `user_progress/service.py` | `user_progress/service.py` projection |
| `content_chunks` (read-only at runtime) | `scripts/ingest_content.py` (offline) | `database/vector_client.py` (read) |

A second writer is a design defect even if the SQL happens to work.

## 7. Fitness-function map

| Rule | Constraint | Mechanism | Failure signal |
|---|---|---|---|
| S1 | One module per SSOT component; nested layout | `pytest-archon` + module-map test | module without a row; flat path |
| S2 | Frozen paths zero diff | CI `git diff --exit-code`; obsoleted grep | any modified line |
| S3 | Docstrings name ADR + INV/REQ | AST docstring check | missing/unknown tag |
| S4 | Import contracts C1-C7 | import-linter + AST | forbidden import |
| S5 | Only config reads env | grep + AST | any other env read |
| S6 | One writer per store | AST write detection + DB grants | a second write path |

Tier 1 runs all of these before Tier 2. A structural failure stops the pipeline.

## 8. Allowed exceptions (with expiry)

| Exception | Applies to | Why | Expires |
|---|---|---|---|
| Composition root imports many routers | `main.py` | It wires the app; no domain decision | When a DI container is introduced |
| Tests import any module | `test/**` | Tests must violate the system | Never |
| Scripts import schemas | `scripts/**` | Validation needs shared types | Never; scripts may not import services |
| Config exempt from S5 | config module | It is the configuration boundary | Never |

No other exception exists.

## 9. Done-when status

- [x] Every rule S1-S6 has a mechanism that fails a build.
- [x] The module table has exactly the 18 SSOT `enforcing_component` modules.
- [ ] Frozen-path list matches `AGENTS.md` and `permission-model.md` after alignment (`DBT-004`).
- [ ] `pytest-archon`, `import-linter`, AST checks and the module-map test exist (`DBT-002`, `DBT-003`).
