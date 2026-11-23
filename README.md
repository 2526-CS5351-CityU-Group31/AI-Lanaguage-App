# AI Language Companion

An AI-powered English learning web app for Chinese-speaking learners (CEFR A1–B2).
A learner chats with an LLM tutor, gets grounded lesson help with citations, receives
writing feedback, reviews vocabulary, and tracks progress. Every model output passes a
**deterministic safety boundary** (scope control + citation validation) before it can
reach the learner.

Built for **CS5351** (CityU Group 31).

> **Branch navigation:** The `main` branch currently holds the core AI foundation, safety
> boundary, and governance baseline. Switch to the
> [`integration/frontend-backend-v1`](https://github.com/2526-CS5351-CityU-Group31/AI-Lanaguage-App/tree/integration/frontend-backend-v1)
> branch for the full-stack application (React UI wired to the FastAPI backend).

## Architecture at a glance

The system is a **guarded monolith** with two zones:

* **Advisory zone (AI component):** `ai_companion/` — prompt assembly, RAG pipeline, retrieval, tutor/provider gateway. May *propose* text and citations, never writes learner state.

* **Authoritative zone (safety boundary):** `safety_boundary/` — `ScopeGuard` (intent classification) and `CitationValidator` (final veto). If validation fails, the output is rejected/abstained, not shown.

```
Browser (React + TypeScript)
  │  HTTPS, Bearer session token
  ▼
FastAPI HTTP boundary  ──►  AuthSecurity (owner-scoped)  ──►  Routers
  ├─ ChatRouter ─► ScopeGuard ─► RagPipeline ─► RetrievalAdapter ─► pgvector (published only)
  │                                 ├─► PromptAssembler
  │                                 ├─► Tutor / provider gateway
  │                                 └─► CitationValidator (veto)
  ├─ ProfileSchema (English / A1–B2 only)
  ├─ VocabularyService / VocabularyLoader
  └─ ProgressService ─► learning_events ─► PostgreSQL

```

Key guarantees: off-topic requests are refused with zero model tokens; citations must
resolve to a retrieved published chunk or the answer abstains; dashboard totals come from
stored events, never from model text; the runtime corpus is read-only (zero upload routes).

## Tech stack

| Layer | Stack | 
| ----- | ----- | 
| Backend | Python 3.12, FastAPI, Uvicorn, psycopg 3 (`[binary,pool]`) | 
| Data | PostgreSQL + pgvector (graceful in-memory fallback for local/dev) | 
| Frontend | React 19, TypeScript, React Router 7, Vite | 
| Frontend tests | Vitest, Testing Library, MSW, jest-axe | 
| LLM provider | CityU gateway — `CS5351/DeepSeek-V4-Flash` (`https://llm.cs.cityu.edu.hk/v1`) | 
| Deploy | Docker (Render web service) + managed PostgreSQL | 

## Repository layout

*(Full-stack layout on `integration/frontend-backend-v1`)*

```
src/backend/
  main.py                 # AppEntry — composition root, server entrypoint
  config.py               # Single environment reader (S5); provider config
  api/
    app.py                # FastAPI app factory (HTTP boundary)
    routers/chat.py       # ChatRouter — scope-guard then run pipeline
    schemas/profile.py    # ProfileSchema — language / CEFR validation
  auth/                   # AuthRouter, AuthSecurity (identity + ownership)
  ai_companion/           # prompt_assembly, rag_pipeline, retrieval_adapter, tutor, provider_gateway
  safety_boundary/        # scope_guard, citation_validator  (authoritative gate)
  contracts/              # Typed DTOs, enums, ports
  db/                     # Connection pool, stores / repositories
  user_progress/          # ProgressService — event-sourced dashboard
  vocabulary/             # VocabularyLoader, VocabularyService
src/frontend/             # React + TypeScript learner UI
  src/api/                # Typed fetch client + endpoint modules
  src/pages/              # Chat, Login, Profile, Progress, Vocabulary
  src/components/         # ChatMessage, SourceCitation, WritingFeedback, ...
  src/tests/              # Vitest + MSW component flow tests
test/offline/             # Deterministic suite (no network, stub model/retrieval)
test/live/                # Controlled provider evaluation (credentials required)
scripts/                  # Governance / validation / eval runners
migrations/               # Ordered SQL migrations
prompts/                  # Versioned prompt files
evals/                    # Evaluation suites
docs/                     # Requirements, architecture, governance artifacts

```

## Getting started

The backend is hosted on **Render**, so you can run the frontend locally and connect
directly to the hosted API without setting up Python or PostgreSQL locally.

### 1. Frontend (connect to Render backend — recommended)

**Prerequisites:** Node.js 20+ (with npm)

```
git checkout integration/frontend-backend-v1
cd src/frontend
npm install

# Point the Vite dev proxy to your Render backend URL
export VITE_API_PROXY_TARGET="https://<your-service>.onrender.com"

npm run dev                        # Vite dev server on http://localhost:5173

```

The Vite dev server proxies `/api/*` requests to `VITE_API_PROXY_TARGET` (defaulting to
`http://localhost:8000` if unset) and strips the `/api` prefix before forwarding (so
`GET /api/me` reaches the backend as `GET /me`).

Open `http://localhost:5173`.

### 2. Local backend (optional — for local/offline development)

**Prerequisites:** Python 3.12+ (PostgreSQL with `pgvector` is optional; the app falls
back to in-memory stores when `DATABASE_URL` is omitted)

```
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Optional: connect to a PostgreSQL instance (e.g., local or Render external DB URL)
# export DATABASE_URL="postgresql://user:password@host:5432/ai_companion"
# psql "$DATABASE_URL" -f migrations/0001_initial_schema_and_roles.sql

# Required only when calling the live LLM provider
export LLM_API_KEY="your-key-here"

python -m src.backend.main         # serves on http://0.0.0.0:8000

```

Health probes: `GET /health` (liveness) and `GET /ready` (readiness incl. DB state).

## API surface

All endpoints accept/return `application/json`. Auth uses a `Bearer` session token in the
`Authorization` header (no cookies persisted client-side, no client-chosen `user_id`).

| Method | Path | Purpose | 
| ----- | ----- | ----- | 
| `POST` | `/auth/register` | Create account, returns session token | 
| `POST` | `/auth/login` | Log in, returns session token | 
| `POST` | `/auth/logout` | End session | 
| `GET` | `/me` | Read own profile | 
| `PATCH` | `/me` | Update own profile (English, A1–B2) | 
| `POST` | `/sessions` | Create a server-generated chat session | 
| `POST` | `/sessions/{session_id}/messages` | Scope-guarded chat turn | 
| `GET` | `/vocabulary/random` | Seeded vocabulary cards for a level | 
| `POST` | `/me/vocabulary/{entry_id}` | Record familiarity state | 
| `GET` | `/me/progress` | Event-aggregated dashboard totals | 
| `GET` | `/health` · `/ready` | Liveness / readiness | 

Chat responses are flat and frontend-friendly: `task`, `abstained`, `source_ids`,
`answer`, `validation_id` (plus `scope_status` / `scope_message` on rejection).

## Testing & verification

### Backend

```
# Deterministic offline suite (no network; stubbed model & retrieval)
pytest test/offline -q

# Strict static analysis
mypy --strict src

# Controlled live provider evaluation (needs LLM_API_KEY)
pytest test/live -q

```

### Frontend

```
cd src/frontend
npm test          # Vitest unit/flow tests
npm run test:a11y # axe accessibility checks
npm run typecheck # tsc --noEmit

```

### Governance gates

CI runs blocking gates on every PR: test approval ordering, static analysis
(`mypy --strict`), offline regression, and semantic evaluation. See
`.github/workflows/ci.yml` and `docs/code-governance/`.

## Deployment

The backend is deployed on **Render** as a Docker image driven by `render.yaml` (Render Blueprint):

* Single web service, `python:3.12-slim`, non-root user, `HEALTHCHECK` on `/health`.

* PostgreSQL with `pgvector` provisioned separately; secrets are configured in the Render dashboard and never committed.

* The server binds the `PORT` injected by the platform.

### Render environment variables

Configure the following environment variables in the Render web service dashboard:

| Key | Required | Purpose / Example Value |
| --- | --- | --- |
| `ENVIRONMENT` | Yes | Runtime environment (`production`) |
| `DATABASE_URL` | Yes | PostgreSQL + `pgvector` connection string (injected from Render PostgreSQL) |
| `SESSION_SECRET` | Yes | Secret key used to sign session tokens (generate a random secret in Render) |
| `CORS_ALLOWED_ORIGINS` | Yes | Comma-separated allowed frontend origins (e.g. `http://localhost:5173` or your deployed frontend URL) |
| `LLM_API_KEY` | Yes | API key for the CityU LLM gateway |
| `LLM_MODE` | Yes | Provider mode (`live` for CityU gateway, `stub` for offline testing) |
| `LLM_MODEL` | Optional | Model identifier (defaults to `CS5351/DeepSeek-V4-Flash`) |
| `EMBEDDING_MODEL` | Optional | Embedding model used for RAG retrieval |
| `EMBEDDING_DIM` | Optional | Vector dimension matching the `pgvector` column (e.g. `1536`) |
| `PROMPT_VERSION` | Optional | Active prompt template version (e.g. `v1.0.0`) |
| `CONTEXT_TOKEN_BUDGET` | Optional | Maximum token budget allocated for assembled context |
| `COMPACTION_MESSAGE_LIMIT` | Optional | Threshold of turns before conversation history compaction triggers |
| `MAX_AI_CALLS_PER_DAY` | Optional | Daily per-user rate limit / quota for LLM calls |
| `LOG_LEVEL` | Optional | Application logging verbosity (`INFO`, `WARNING`, `DEBUG`) |

## Documentation

Architecture and governance artifacts live under `docs/` and the repository root, and are
the authoritative reference:

* `architecture-blueprint.md` — boundaries, components, authority

* `docs/req/requirements.yaml` — requirement registry (single source of truth)

* `docs/architecture/invariants.md` — non-negotiable guarantees

* `docs/architecture/adr/` — architecture decision records

* `docs/code-governance/` — structural & verification constraints

## Branching

| Branch | Contents | 
| ----- | ----- | 
| `main` | Core AI foundation, safety boundary, and governance baseline | 
| `backend` | Backend API, PostgreSQL/pgvector ingestion, and smoke tests | 
| `frontend` | Frontend React + TypeScript development | 
| `integration/frontend-backend-v1` | **Full stack** — React UI wired to FastAPI backend | 