# Role ownership map - baseline R1

**Purpose:** for a tight-deadline team with no always-on coding supervision, make each teammate's writable domain explicit so a PM can review any pull request with one question: *"Does this diff stay inside the author's lane?"*

**Source of truth:** the per-requirement `owner` and `enforcing_component` fields in `docs/req/requirements.yaml`. This file is a derived, human-readable view; if it disagrees with the registry, the registry wins for *accountability*, but the **working lane** (who writes the code) is defined here and may deliberately differ from the accountability owner.

**Rule:** a teammate may create/modify files only in their own rows below. A change that needs a path outside the lane must be requested from that lane's owner (or approved by the PM) in the PR description, not made silently.

## 1. Ownership by role

| Team member | Owns (writable) | Must not modify | Primary app area |
|---|---|---|---|
| **Member 1 (Adrian)** | `.github/workflows/ci.yml`, `docs/code-governance/ai-use-log.yaml` (append only), docs/architecture registers they author | `src/**` (unless assigned below) | PM / governance / CI |
| **Member 2 (Leon)** | `src/backend/ai_companion/**` (`retrieval_adapter.py`, `rag_pipeline.py`, `tutor.py`), `src/backend/grammar/**`, `src/backend/safety_boundary/evaluator.py`, `src/backend/safety_boundary/citation_validator.py`, `scripts/ingest_content.py` | `auth/**`, `api/**`, `user_progress/**`, `vocabulary/**` | AI / RAG / writing feedback / content ingest |
| **Member 3 (Kapo)** | `src/backend/auth/**` (`router.py`, `security.py`), `src/backend/api/**` (`routers/chat.py`, `schemas/profile.py`), `src/backend/safety_boundary/scope_guard.py`, `src/backend/user_progress/service.py`, `src/backend/vocabulary/**` | `ai_companion/**` (except co-owned), `database/**` | Auth / API / scope guard / vocabulary / progress |
| **Member 4 (Henry)** | `src/backend/user_progress/service.py` (dashboard metrics), progress-related frontend views | `auth/**`, `ai_companion/**`, `safety_boundary/**` | Progress dashboard |
| **Member 5 (Luming)** | `.github/workflows/ci.yml` (co-owned), `docker-compose.yml`, `.env.example`, `scripts/**` (CI/eval/test runners), `test/**` (suite design & approval), `docs/debt-register.md` / `bug-diary.md` / `review-memo.md` (QA registers) | application feature code (implemented by the domain owner) | **QA / DevOps / governance**: CI gates, test-suite design, quality gates, release checks |
| **Member 5 (co-accountability)** | Accountability owner (not implementer) for `src/backend/database/vector_client.py`, `src/backend/main.py`, `src/backend/ai_companion/tutor.py`, `src/backend/ai_companion/prompt_assembly.py` | — | Verifies these modules against their tests; the **domain implementer** (Member 2/3) writes them |

**Co-owned paths** (two names listed): changes to `user_progress/service.py` (Member 3 + 4) and `.github/workflows/ci.yml` (Member 1 + 5) require both owners to agree in review.

**Member 5 is an accountability owner, not an implementer, for four code modules.** The SSOT `requirements.yaml` names Member 5 as `owner` of `INV-SEC-001` (`vector_client.py`), `INV-SEC-002` (`main.py`), `NFR-PERF-001` (`tutor.py`) and `NFR-SEC-001` (`prompt_assembly.py`). To keep Member 5 focused on QA/DevOps/governance, those modules are **implemented by the domain owner** (Member 2 for `ai_companion/*`, Member 3 for `database/*` and `main.py`) and **QA-verified by Member 5** against their tests. The registry keeps Member 5 as the accountability owner for traceability; the table above reflects who actually writes the code.

**Human-only gates** (no one may modify without a human author + ADR; see `permission-model.md` §2): `src/backend/safety_boundary/scope_guard.py`, `src/backend/safety_boundary/citation_validator.py`, `src/backend/auth/security.py`. These are assigned above for planning, but implementation follows the gate process.

## 2. PM pull-request check (three questions only)

For every PR, the PM checks:

1. **Lane:** does the diff touch only the author's "Owns" paths? (If not, was it requested/approved in the PR description?)
2. **Traceability:** does the change name at least one `INV-` / `FR-` / `NFR-` ID from `docs/req/requirements.yaml` in its description or test docstrings?
3. **Log:** does `docs/code-governance/ai-use-log.yaml` have a new session entry for code/prompt changes? (CI Gate 6 also enforces this.)

If all three pass, the PR is approvable on governance grounds. Deeper correctness is the owner's responsibility and the test suite's job.

## 3. How each teammate starts a session

Give each teammate this one line at the start of their work:

> "You own `<paths from your row>`. Read `AGENTS.md` first, then the artifacts it lists. Do not modify paths outside your lane; if you believe you must, stop and ask the PM."

## 4. Known limitation (for the report)

Role boundaries here are **declared and review-enforced**, not technically blocked. The `permissions.jsonc` hooks that would reject an out-of-lane write are planned (`DBT-004`). Until they exist, containment relies on the PM check in §2 plus the per-session instruction in §3.
