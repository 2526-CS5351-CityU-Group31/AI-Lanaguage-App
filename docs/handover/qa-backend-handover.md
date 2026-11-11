# QA Handover — Backend Lane (Member 3 / Kapo)

**Date:** 2026-11-08
**From:** Member 3 (Kapo) — Backend & Data
**To:** Member 5 (Luming) — QA / DevOps / Governance
**Baseline:** R1 · **Scope:** backend deliverable, pre-formal-test

---

## 1. Executive Summary

The Member 3 backend lane is **feature-complete, smoke-tested, and deployed**.

- **Smoke test:** 14/14 core flows PASS against the live Postgres deployment (auth, profile,
  language/CEFR boundary, scope control, progress, logout/revocation, persistence across a
  fresh connection). Two earlier ScopeGuard findings (tech-action prompt → `mixed`;
  morphology question → `uncertain`) were fixed by the human gate author and re-verified.
- **Deployment:** live on Render (Docker) with a managed PostgreSQL 16 instance.
- **Outstanding for QA:** the formal offline suite does not exist yet (`test/offline/` is empty).
  That is intentionally handed to Member 5 — see §5.

### Live endpoints

| Item | URL |
|---|---|
| Base URL | `https://ai-lanaguage-app.onrender.com` |
| Swagger UI | `https://ai-lanaguage-app.onrender.com/docs` |
| ReDoc | `https://ai-lanaguage-app.onrender.com/redoc` |
| OpenAPI JSON (Postman import) | `https://ai-lanaguage-app.onrender.com/openapi.json` |
| Liveness | `GET /health` → `{"status":"ok"}` |
| Readiness | `GET /ready` → 200 ready / 503 when DB unavailable (RP-011) |

**Registered routes:** `/auth/register`, `/auth/login`, `/auth/logout`, `/me` (GET/PATCH),
`/me/progress`, `/me/vocabulary/{entry_id}`, `/vocabulary/random`, `/sessions/{session_id}/messages`,
`/health`, `/ready`. **Zero upload/multipart routes** (INV-SEC-002).

> Note: `/health` is a static liveness probe; readiness is `/ready`. On the Render **Free**
> plan the instance sleeps when idle — the first request after sleep incurs a cold start
> (ADR-011 RP-018).

---

## 2. Architecture & Data Persistence

- **Driver:** `psycopg[binary,pool]` 3.3.8 — synchronous connection pool
  (`src/backend/db/repositories.py::make_pool`), min 1 / max 5, `dict_row` factory.
- **Repositories** (Postgres implementations of the in-memory protocol, so services are unchanged):
  - `PostgresUserRepository` — users
  - `PostgresSessionRepository` — sessions (token stored hashed)
  - `PostgresVocabularyStore` — user_vocabulary
  - `PostgresEventStore` — learning_events (append-only, idempotent)
- **Lifecycle:** pool opened in the FastAPI `lifespan` startup and closed on shutdown
  (`src/backend/api/app.py`). If the DB is unreachable the app degrades to in-memory stores
  and logs a warning (`src/backend/main.py::build_stores`); `/ready` then reports 503.
- **Migration:** `migrations/0001_initial_schema_and_roles.sql` — 7 tables
  (`users`, `sessions`, `user_vocabulary`, `learning_events`, `content_sources`,
  `content_chunks`, `content_audit`), pgvector + HNSW index, and the role grants below.
  **Applied to the Render instance.**

### Security grants (verified live)

| Role | Corpus (`content_*`) | `learning_events` | Learner tables |
|---|---|---|---|
| `app_runtime` | **SELECT only** (INSERT/UPDATE/DELETE denied) | **INSERT + SELECT only** (no UPDATE/DELETE) | SELECT/INSERT/UPDATE/DELETE |
| `ingest_admin` | write (offline only) | — | — |

- **INV-SEC-001** — corpus is read-only under the runtime role; verified `INSERT`/`UPDATE`/`DELETE`
  on `content_*` all raise `InsufficientPrivilege`.
- **INV-PROG-001** — `learning_events` is append-only under the runtime role; verified `UPDATE`/
  `DELETE` denied.

> **Action for Luming:** the live Render web service currently connects with the DB **owner**
> role (`app_6hu8_user`), which bypasses grants. To make INV-SEC-001/INV-PROG-001 enforced at
> runtime, set the service `DATABASE_URL` to the internal `app_runtime` DSN. Local `.env`
> already uses `app_runtime`.

---

## 3. Gate Modules & Invariant Coverage (14 Kapo-owned requirements)

### AuthSecurity — `src/backend/auth/security.py` (human-authored gate)
Session identity and per-record authorization.
- Password hashing via a memory-hard KDF; tokens random, stored **hashed**.
- Principal derived **only** from the session; payload `user_id` is ignored.
- Owner-scoped record access; foreign id → **404 with empty body, zero mutation**.
- Covers **INV-AUTH-001**; CEFR/language enforcement at the boundary via `ProfileSchema`
  (**INV-CEFR-001**, **INV-LANG-001**).

### ScopeGuard — `src/backend/safety_boundary/scope_guard.py` (human-authored gate)
Deterministic intent classifier; runs **before** any retrieval/model call.
- Statuses: `accepted` / `rejected` (exact `FIXED_REFUSAL`) / `uncertain` (fixed clarification) /
  `mixed` (fixed resubmit).
- Covers **INV-SCOPE-001, 002, 004, 005**; **NFR-QUAL-004**.
- **INV-SCOPE-003** (zero retrieval/LLM calls on rejection) enforced in
  `src/backend/api/routers/chat.py`.

### UserProgress — `src/backend/user_progress/service.py`
- Dashboard totals are a read-time projection over stored events, **never model output**.
- Append-only, idempotent event writes (`(user_id, idempotency_key)` unique).
- Covers **INV-PROG-001**; **FR-DASH-001** aggregation.

### Full Kapo requirement → test map

| Requirement | Enforcer | Test target (to be created) |
|---|---|---|
| INV-SCOPE-001 | safety_boundary/scope_guard.py | `test/offline/test_safety_boundary/test_scope_guard.py::test_scope_pipeline_execution_order` |
| INV-SCOPE-002 | safety_boundary/scope_guard.py | `…::test_fixed_refusal_response` |
| INV-SCOPE-003 | api/routers/chat.py | `…::test_zero_calls_on_rejection` |
| INV-SCOPE-004 | safety_boundary/scope_guard.py | `…::test_uncertain_intent_clarification` |
| INV-SCOPE-005 | safety_boundary/scope_guard.py | `…::test_mixed_intent_blocking` |
| INV-AUTH-001 | auth/security.py | `test/offline/test_auth/test_authorization.py::test_cross_user_isolation` |
| INV-LANG-001 | api/schemas/profile.py | `test/offline/test_auth/test_profile.py::test_reject_non_english` |
| INV-CEFR-001 | api/schemas/profile.py | `test/offline/test_auth/test_profile.py::test_reject_invalid_cefr` |
| INV-PROG-001 | user_progress/service.py | `test/offline/test_user_progress/test_dashboard.py::test_progress_derived_from_events` |
| FR-AUTH-001 | auth/router.py | `test/offline/test_auth/test_auth_flow.py::test_register_login` |
| FR-PROF-001 | auth/router.py | `test/offline/test_auth/test_profile.py::test_update_profile` |
| FR-VOC-001 | vocabulary/loader.py | `test/offline/test_vocabulary/test_loader.py::test_random_selection_with_seed` |
| FR-VOC-002 | vocabulary/service.py | `test/offline/test_vocabulary/test_service.py::test_record_familiarity` |
| NFR-QUAL-004 | safety_boundary/scope_guard.py | `…::test_off_topic_refusal_accuracy` |

---

## 4. Smoke Test Evidence (2026-11-08, live Postgres, real gates)

| Test | Endpoint | HTTP | Verdict |
|---|---|---|---|
| Health | GET /health | 200 | ✅ |
| Register | POST /auth/register | 200 | ✅ (returns 200, spec text says 201) |
| Get profile | GET /me | 200 | ✅ |
| Update CEFR valid | PATCH /me | 200 | ✅ |
| Update CEFR invalid (`C1`) | PATCH /me | 422 | ✅ INV-CEFR-001 |
| Non-English register | POST /auth/register | 422 | ✅ INV-LANG-001 |
| In-scope question | POST /sessions/s1/messages | 200 | ✅ |
| Out-of-scope | POST /sessions/s1/messages | 200 | ✅ FIXED_REFUSAL |
| Empty/ambiguous | POST /sessions/s1/messages | 200 | ✅ clarification |
| Tech-action prompt (fixed) | POST /sessions/s1/messages | 200 | ✅ rejected |
| Morphology question (fixed) | POST /sessions/s1/messages | 200 | ✅ accepted |
| Post learning event | POST /me/vocabulary/w1 | 200 | ✅ |
| Dashboard | GET /me/progress | 200 | ✅ `words_reviewed/mastered` |
| Logout | POST /auth/logout | 204 | ✅ |
| Token after logout | GET /me | 401 | ✅ revoked |
| Persistence (new pool) | — | — | ✅ |

---

## 5. QA Action Items for Luming

1. **Scaffold `test/offline/`** and implement the 14 targets in the table in §3. Suggested layout:
   `test/offline/test_auth/`, `test_safety_boundary/`, `test_user_progress/`, `test_vocabulary/`.
   - Offline tests must use in-memory stores / stub adapters — **no network, no provider calls**
     (`verification-constraints.md §6`).
   - Every test docstring must name its `INV-/FR-/NFR-` ID (V3 traceability).
   - Each invariant test must exercise the **violation path** and fail on a deliberately broken build (V2).
2. **CI execution (Gate 2 & Gate 6):**
   - Gate 2 (Static Analysis) currently runs a placeholder — wire `mypy --strict src` and
     `pytest test/offline -q`.
   - Gate 5 (Regression) currently echoes — run `pytest test/offline -q`.
   - Gate 6 (AI-Use Log) is implemented; confirm SES-026 is present in
     `docs/code-governance/ai-use-log.yaml` (it validates against the schema).
3. **Negative boundary probes to include:**
   - Foreign `user_id` / session id → **404 with empty body, zero state mutation**
     (20-probe suite per `permission-model.md §2`).
   - Unauthenticated writes (POST /me/vocabulary, PATCH /me) → **401**.
   - Forged/expired token → no principal; after logout → 401.
   - `learning_events` UPDATE/DELETE as `app_runtime` → permission-denied (INV-PROG-001).
   - Corpus INSERT/UPDATE/DELETE as `app_runtime` → permission-denied (INV-SEC-001).
4. **Known gaps / notes:**
   - `FR-VOC-001` returns **503** until `content/vocabulary_en.json` exists (content owner lane).
   - Live service `DATABASE_URL` still uses the owner role — switch to `app_runtime` to enforce grants.
   - `scope_guard.py` / `security.py` are **human-authored gate modules**; any change to their
     enforcement logic needs ADR + failing-before/passing-after test + two reviewers.

---

## 6. Reference Commands

```bash
# Offline suite (once implemented)
pytest test/offline -q

# Static typing gate
mypy --strict src

# Canonical gate block (byte-identical to verification-constraints.md §2)
python scripts/validate_req.py docs/req/requirements.yaml
python scripts/check_trace.py
python scripts/check_permissions.py
python scripts/check_manifest.py
pytest test/structural -q
```

**Handover accepted by:** Member 5 (Luming) _________________  **Date:** ______
