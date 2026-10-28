# Structural constraints - baseline R1

**Purpose:** state how code must be organised, extended and bounded, so the rules apply regardless of which element is being built.
**Consumers:** Build agent (every file it writes), Tier-1 fitness functions, reviewers.
**Owner:** Member 3 (Backend & Data); enforcement co-owned by Member 5.
**Status:** declared. No source file exists at baseline; the mechanisms below are the required checks, not a claim that they run. Implementation is tracked by `DBT-002` and `DBT-003`.

## 1. Module organisation (S1)

**Rule:** each architectural element maps to exactly one module; the module is named after the element in snake_case; one element has one primary class. A module that contains two elements forces every change to touch unrelated behaviour and makes the import boundary unprovable.

| Element | Module | Class | Pattern / ADR | Imports from |
|---|---|---|---|---|
| `ApiGateway` | `src/api_gateway.py` | `ApiGateway` | Gateway / composition root, ADR-001 | contracts, request_authenticator, learner_profile_service, practice_session_service, writing_feedback_service, vocabulary_service, assessment_service, progress_ledger, content_publisher, tutor_pipeline, config |
| `RequestAuthenticator` | `src/request_authenticator.py` | `RequestAuthenticator` | Guard, ADR-001 | contracts, db, config, observability_store |
| `OwnershipGuard` | `src/ownership_guard.py` | `OwnershipGuard` | Guard, ADR-001 | contracts, db, observability_store |
| `LearnerProfileService` | `src/learner_profile_service.py` | `LearnerProfileService` | Service, ADR-001 | contracts, db, ownership_guard, config |
| `PracticeSessionService` | `src/practice_session_service.py` | `PracticeSessionService` | Service + checkpoint state, ADR-008/009 | contracts, db, ownership_guard, observability_store, config |
| `WritingFeedbackService` | `src/writing_feedback_service.py` | `WritingFeedbackService` | Service, ADR-005 | contracts, db, ownership_guard, tutor_pipeline, observability_store |
| `VocabularyService` | `src/vocabulary_service.py` | `VocabularyService` | Service, ADR-008 | contracts, db, ownership_guard |
| `AssessmentService` | `src/assessment_service.py` | `AssessmentService` | Policy/service, ADR-008 | contracts, db, ownership_guard, tutor_pipeline, progress_ledger, observability_store |
| `ProgressLedger` | `src/progress_ledger.py` | `ProgressLedger` | Event store + projection, ADR-008 | contracts, db, ownership_guard |
| `ContentPublisher` | `src/content_publisher.py` | `ContentPublisher` | Publisher / state machine, ADR-007 | contracts, db, ownership_guard, config, observability_store |
| `RetrievalService` | `src/retrieval_service.py` | `RetrievalService` | Port adapter, ADR-007 | contracts, db, config |
| `PromptAssembler` | `src/prompt_assembler.py` | `PromptAssembler` | Builder, ADR-006 | contracts, config, session_summary_store |
| `ModelGateway` | `src/model_gateway.py` | `ModelGateway` | Adapter + circuit breaker, ADR-005 | contracts, config, observability_store |
| `ResponseValidator` | `src/response_validator.py` | `ResponseValidator` | Specification / pure function, ADR-005 | contracts, config |
| `DegradationController` | `src/degradation_controller.py` | `DegradationController` | Policy/strategy, ADR-001, RP catalog | contracts, config, observability_store |
| `TutorPipeline` | `src/tutor_pipeline.py` | `TutorPipeline` | Orchestrator, ADR-001/005 | contracts, retrieval_service, prompt_assembler, model_gateway, response_validator, degradation_controller, observability_store, config |
| `SessionSummaryStore` | `src/session_summary_store.py` | `SessionSummaryStore` | Repository, ADR-009 | contracts, db, ownership_guard, config |
| `ObservabilityStore` | `src/observability_store.py` | `ObservabilityStore` | Audit appender, ADR-009 | contracts, db, config |
| `AppConfig` | `src/config.py` | `AppConfig` | Configuration object, `configuration-governance.md` | contracts (stdlib + typing only) |

**Support packages (not architectural elements):**

| Package | Contains | Imports allowed | Rule |
|---|---|---|---|
| `src/contracts/` | Pydantic DTOs, enums, ports, error types | stdlib, pydantic | No imports from any element; no I/O |
| `src/db/` | Engine, session factory, repository primitives, migrations runner | contracts, config | No imports from services; no domain rules |

**S1 enforcement:** `pytest-archon` enforces one primary class per module and the module/class naming pattern; `test/structural/test_module_map.py` compares the AST module list to this table. A new module without a row fails Tier 1.

## 2. Extension, never replacement (S2)

**Rule:** a new design round extends the baseline. Existing contracts, accepted ADRs, applied migrations and published content versions are immutable; a revision build carries a delta specification with four lists:

```
OBSOLETED:  element/module/contract removed from service
ADDED:      new element/module/contract
MODIFIED:   changed contract with old -> new and the ADR that justifies it
FROZEN:     paths that must show zero diff in this round
```

- An `OBSOLETED` element must have **zero imports** after the round. This is a grep/AST check, not an opinion.
- A revision never edits the prior round's frozen files to "clean up"; it adds a new version and records the delta.
- A change to a frozen path requires an ADR and a human approver; the old row is marked `Superseded` or `retired`, never deleted.

| Frozen path | Frozen in | Zero-diff check |
|---|---|---|
| `docs/req/requirements.yaml` | R1 | baseline delta only |
| `docs/architecture/adr/001-*.md`, `005-*.md` ... `010-*.md` | R1 | append-only; supersede with a new ADR |
| `architecture-blueprint.md` | R1 | ADR + human approval |
| `prompts/prompt_v1.0.0.yaml` | R1 | new version file on change |
| `evals/EVAL-1.0.0.yaml` | R1 | new eval version on change |
| Applied `migrations/*.sql` | R1 | new migration only |
| Published `content/` versions | R1 | retire, never edit |
| `.opencode/rules.md`, `.opencode/permissions.jsonc`, `.github/workflows/ci.yml` | R1 | human-only writes |

**S2 enforcement:** CI `git diff --exit-code -- <frozen path>` for each row; a non-zero diff fails. A revision build also runs `grep -r "<ObsoletedElement>" src/` and expects zero matches.

## 3. ADR and invariant traceability in code (S3)

**Rule:** every module states which element it implements and which ADR governs it; every non-trivial public function names the ADR section and the invariant it implements.

Module docstring format:

```python
"""ResponseValidator - the single authoritative gate for model output.

Element: ResponseValidator
Implements: ADR-005 §Decision, §Response contracts; INV-001, INV-002, INV-007
"""
```

Function docstring format:

```python
def validate_citations(output: TutorOutput, evidence: EvidenceSet) -> Verdict:
    """Reject any source id outside the retrieved published set.

    Implements: ADR-005 §Rejection codes; INV-002; REQ-LANG-INV-002
    """
```

- "Non-trivial" means any public function with a branch, a loop, I/O or a security consequence; a one-line property getter may omit the tag.
- The tag pattern is `ADR-[0-9]{3}` and `INV-[0-9]{3}` and `REQ-LANG-...`; `test/structural/test_docstring_trace.py` parses the AST and fails on a missing tag.
- A docstring that names a non-existent ADR or invariant is a failure, not a warning.

## 4. Authority and import boundaries (S4)

| Contract | Rule | Mechanism | Failure signal |
|---|---|---|---|
| C1 - single gate | `response_validator` may be imported only by `tutor_pipeline` (and tests) | import-linter forbidden contract | any other importer |
| C2 - model adapter | `model_gateway` may be imported only by `tutor_pipeline` (and tests) | import-linter | another importer |
| C3 - retrieval adapter | `retrieval_service` may be imported only by `tutor_pipeline` (and tests) | import-linter | another importer |
| C4 - context builder | `prompt_assembler` may be imported only by `tutor_pipeline` (and tests) | import-linter | another importer |
| C5 - failure policy | `degradation_controller` may be imported only by `tutor_pipeline` (and tests) | import-linter | another importer |
| C6 - no write from the pipeline | `tutor_pipeline` must not import `db`, `api_gateway`, or any domain service except `observability_store` and `config` | import-linter forbidden contract + AST | any db/domain import |
| C7 - memory isolation | `session_summary_store` must not be imported by `assessment_service`, `progress_ledger`, `ownership_guard`, `request_authenticator`, `content_publisher` | import-linter forbidden contract | any decision-service import |
| C8 - ownership guard | every record service imports `ownership_guard`; the guard imports no service | import-linter + required-import rule | a record service without the guard |
| C9 - no gateway import | no `src/` module may import `api_gateway` | import-linter | any importer |
| C10 - no learner service in content path | `content_publisher` and `retrieval_service` must not import learner services | import-linter | any importer |
| C11 - single writer | each store has exactly one writing module (S6 table) | AST write-detection + DB grants | a second writer |
| C12 - config boundary | only `config.py` may reference `os.environ`, `os.getenv` or `dotenv` | AST + grep | any other reference |

The gate is callable only from the adjudicator (`TutorPipeline`). A circuit breaker, rate limiter or retry wrapper may wrap `ModelGateway`, never `ResponseValidator`, `OwnershipGuard` or `AssessmentService`.

## 5. Configuration boundary (S5)

- `src/config.py` is the only module that reads the environment; every other module receives a frozen `AppConfig`.
- A new config key requires a row in `configuration-governance.md`, validation, a startup test and, if it changes behaviour, an ADR.
- `grep -rn "os\.environ\|os\.getenv\|load_dotenv" src --include='*.py' | grep -v '^src/config.py:'` must produce no output.
- A module that constructs its own config or reads an env var after startup fails Tier 1.

## 6. Single-writer stores (S6)

| Store | Sole writer | Allowed readers |
|---|---|---|
| `practice_sessions`, `messages` | `PracticeSessionService` | owned reads, `PromptAssembler` (recent turns) |
| `turn_checkpoints` | `PracticeSessionService` | the same service |
| `writing_submissions`, `feedback` | `WritingFeedbackService` | owner reads |
| `vocabulary`, `user_vocabulary` | `VocabularyService` | owner reads |
| `quizzes`, `quiz_items`, `attempts` | `AssessmentService` | owner reads, `ProgressLedger` (event refs) |
| `learning_events` | `ProgressLedger` | `ProgressLedger` projection only |
| `content_sources`, `content_versions`, `content_chunks` | `ContentPublisher` | `RetrievalService` (active), admin audit |
| `session_summaries` | `SessionSummaryStore` | `PromptAssembler`, learner settings |
| `observability_events` | `ObservabilityStore` | operator metrics only |
| `ai_usage_daily` | `ModelGateway` | cost report |

A second writer is a design defect even if the SQL happens to work. Database grants should make the single writer visible: the application role for a service is granted `INSERT` only on its own tables where the deployment permits it.

## 7. Fitness-function map

| Rule | Constraint | Applies to | Mechanism | Failure signal |
|---|---|---|---|---|
| S1 | One element = one module; module name = element name | `src/**` except `contracts/`, `db/` | `pytest-archon` single-class + naming test; module map test | two elements in one file, or a module without a row |
| S2 | New code extends; frozen paths zero diff | frozen paths table | CI `git diff --exit-code -- <path>`; obsoleted grep | any modified line; any import of an obsoleted element |
| S3 | Module/function docstrings name ADR + INV | `src/**` | AST docstring check | missing or unknown tag |
| S4 | Import contracts C1-C12 | `src/**` | import-linter + AST | a forbidden import or a missing guard |
| S5 | Only `config.py` reads the environment | `src/**` | grep + AST | any other `os.environ`/`getenv` |
| S6 | One writer per store | `src/**` | AST write detection + DB grants | a second write path |

Tier 1 runs all of these before Tier 2. A structural failure stops the pipeline; it is not downgraded to a review comment.

## 8. Allowed exceptions (with expiry)

| Exception | Applies to | Why | Expires |
|---|---|---|---|
| Composition root imports many services | `api_gateway.py` | It wires the application; it contains no domain decision | When a dependency-injection container is introduced (round 2 at the earliest) |
| Tests import any element | `test/**` | Tests must construct and violate the system | Never; tests are outside `src/` |
| Scripts import contracts/config | `scripts/**` | Validation and reporting need shared types | Never; scripts may not import services |
| Support packages exempt from S1 | `src/contracts/`, `src/db/` | They are not architectural elements | Never; they may not grow domain logic |
| `config.py` exempt from S5 | `src/config.py` | It is the configuration boundary | Never |

No other exception exists. An exception not in this table is a violation, even if it is convenient.

## 9. Done-when status

- [x] Every rule S1-S6 has a mechanism that fails a build, not a reviewer's memory.
- [x] The module table has exactly the 19 elements in blueprint §4, with the same names.
- [ ] The frozen-path list matches `AGENTS.md` and `permission-model.md` after `AGENTS.md` is written (`DBT-004`).
- [ ] `pytest-archon`, `import-linter`, AST checks and the module-map test exist and run in Tier 1 (`DBT-002`, `DBT-003`).
- [ ] A deliberately broken import is shown to fail the gate and preserved as evidence (`DBT-003`).
