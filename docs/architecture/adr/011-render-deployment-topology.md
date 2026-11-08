# ADR-011: Deploy the guarded monolith to Render (single web service + managed PostgreSQL)

- **Status:** Accepted
- **Date:** 2026-11-06
- **Supersedes:** -
- **Superseded by:** -
- **Decision owner:** Member 3 (Backend & Data), co-signed by Member 5 (QA & DevOps)
- **Related requirements:** INV-SEC-001, INV-SEC-002, INV-PROG-001, NFR-PERF-001, NFR-COST-001, NFR-GOV-001, FR-AUTH-001, FR-DASH-001
- **Related artifacts:** `architecture-blueprint.md` §3.1, §8, §10; `docs/architecture/adr/001-guarded-monolith.md`; `docs/architecture/adr/009-learner-data-isolation.md`; `docs/architecture/adr/010-agent-tool-boundary.md`; `docs/architecture/configuration-governance.md`; `docs/architecture/runtime-policy-catalog.md`; `docs/code-governance/structural-constraints.md` S5, S6
- **Review triggers:** cold-start rate > 5% of production requests in a rolling week; `tutor_response_p95_seconds > 12` for 3 consecutive days; free-tier instance-hour budget exceeded; any move off the selected region; a request to scale horizontally; any provider-region change that adds > 100 ms round-trip to the LLM provider.

## Context

ADR-001 chose a guarded monolith: one FastAPI backend and one PostgreSQL (pgvector) database. R1 needs a concrete hosting topology so the team can deploy, prove the invariants on the deployed build, and roll back. The hosting choice is constrained by four things that cannot be traded away:

- **Invariant provability (INV-SEC-001).** The runtime application must reach the vector content through a read-only database role. The topology must make that role separation a real grant, not a code convention.
- **Isolation (INV-AUTH-001, ADR-009).** Learner data lives in the same PostgreSQL instance as the corpus; the role split must not create a second write path to `learning_events` or `user_vocabulary`.
- **Cost durability (NFR-COST-001, RP-008).** The per-user daily AI call cap must survive a process restart. A platform that spins processes down and up must not reset the counter.
- **Latency (NFR-PERF-001).** A turn p95 must stay at or below 12.0 s. Process cold start and cross-region round-trips both consume that budget.

The team has no dedicated operations engineer and a five-sprint deadline, so the topology must be low-maintenance and reproducible from the repository.

## Decision

Deploy as **one Render Web Service (Free instance) running the FastAPI app behind Render's managed HTTPS**, plus **one Render PostgreSQL instance with the `pgvector` extension**. The runtime connects with a dedicated **read-only vector role** for corpus access and a separate owner role for the application's own tables. Configuration is injected through Render's environment/secret group; secrets never live in the repository. Free-tier spin-down is accepted, and its consequences are handled explicitly rather than hidden.

### Role split (INV-SEC-001)

| Role | Used by | Grants |
|---|---|---|
| `app_runtime` | Render web service | `CONNECT`; `SELECT` on `content_chunks`; `SELECT/INSERT/UPDATE/DELETE` on learner-scoped tables (`users`, `sessions`, `user_vocabulary`, `learning_events`) **only**; no DDL; no write on `content_chunks` |
| `ingest_admin` | Offline ingestion (`scripts/ingest_content.py`) only | DDL + write on `content_chunks`; never present in the Render environment |
| `owner` | Human/migration path | Full schema ownership; used by migrations before first apply |

The application DB pool binds `app_runtime`. Any `INSERT/UPDATE/DELETE` against `content_chunks` through the web service raises a permission-denied error, which is the enforcement the INV-SEC-001 test asserts.

### Configuration (S5, configuration-governance)

- All keys are defined in `docs/architecture/configuration-governance.md`. Two additions are required for this topology:
  - `PORT` — injected by Render; consumed only by the configuration module so that S5 ("only config reads `os.environ`") still holds.
  - `APP_ENV` stays `ENVIRONMENT=prod` in the Render group; prod validation rules (§3) apply unchanged.
- Secrets (`DATABASE_URL`, `SESSION_SECRET`, `LLM_API_KEY`) are stored in the Render secret group and never echoed by the fail-loud startup check (§3; `guard_secret`).
- Non-secret defaults for `prod` live in the committed `config/prod.yaml`; environment variables override them per §1 precedence.

### Free-tier spin-down and the latency budget (NFR-PERF-001)

Render Free instances sleep after idle and incur a cold start of roughly 30-50 s on the next request. This exceeds the 12.0 s turn target for the first request after sleep. The decision accepts this and records the mitigations:

1. `NFR-PERF-001` is measured on **warm** instances (the load test establishes a warm baseline before sampling), which matches how the requirement is scoped to tutor response generation, not to platform wake-up.
2. An external keep-alive probe may keep the service warm during a demo or evaluation window; this is owned by Member 5 and is **not** part of the application.
3. Cold-start frequency is emitted as `cold_start_total` and watched by the review trigger above.

### Cost-cap durability (NFR-COST-001, RP-008 / RP-018)

Because the Free plan restarts processes, the per-user daily AI call counter is **stored in PostgreSQL**, not in process memory. A spin-down therefore does not reset RP-008. This is a hard consequence of the platform choice, not an optional optimization.

### Readiness and failure behaviour (RP-011)

`GET /health` is a static 200 (liveness). `GET /ready` performs the database probe and returns 503 when the store is unreachable, matching RP-011; Render health checks bind to `/health` so a transient DB outage does not cause an unnecessary restart loop.

## Consequences

**Benefits**

- Lowest operational and monetary cost for a five-member student team; one service and one database mirror ADR-001 exactly.
- The read-only vector role is a real grant on a managed instance, making INV-SEC-001 provable on the deployed build, not just in tests.
- Configuration stays in one place and fails loudly at startup, so a misconfigured deploy dies at boot rather than misbehaving at runtime.

**Costs / accepted risks**

- **Cold start exceeds the latency target for first requests.** Accepted; measured warm, watched by `cold_start_total`, optionally mitigated by an external keep-alive.
- **No high availability.** A Free instance and a single database are single points of failure; consistent with ADR-001's "no HA in R1".
- **Horizontal scale-out is unavailable on Free.** Accepted; a review trigger fires if sustained load requires it.
- **Instance-hours cap.** Free instance time is limited; long-running always-warm keep-alive competes with the limit. The team must balance warm-time against the monthly allowance.
- **Region lock.** The service and database should share a region near the LLM provider endpoint to keep round-trips small; moving either is a review trigger.

## Rollback plan

1. **App rollback:** Render keeps prior deploys; roll back to the previous successful deploy image. No database change is required because migrations are append-only (`structural-constraints.md` S2).
2. **Migration rollback:** applied migrations are immutable; a rollback is a new corrective migration, never an edit.
3. **Config rollback:** revert the environment/secret group to the previous known-good values; the fail-loud startup check prevents a half-valid config from serving.
4. **Full teardown:** delete the web service; the managed database can be restored from its Render backup. Retrieval and AI features fail closed per RP-004/RP-006 while the service is down.

## Responsibility map

| Concern | Implemented / owned by |
|---|---|
| App process and Dockerfile | Member 3 (implementer) with Member 5 (DevOps review) |
| DB role grants (`app_runtime`, `ingest_admin`) | Member 3; migrations reviewed by Member 5 |
| `PORT`/`ENVIRONMENT` config key and validation | Member 3 (`config` module) |
| Keep-alive probe / instance-hour budget | Member 5 (DevOps) |
| CI deploy step, CI secrets | Member 5 (`.github/workflows/ci.yml` is human-only) |
| Read-only grant test (INV-SEC-001) | Member 5 (QA) authors, Member 3 implements |

## Deployment artefacts

| File | Purpose | Owner |
|---|---|---|
| `Dockerfile` | Pinned Python 3.12-slim image; non-root user; CMD `python -m src.backend.main`; HEALTHCHECK on `/health` | Member 3 (implementer), reviewed by Member 5 |
| `render.yaml` | Render Blueprint: one free web service + one free Postgres(pgvector); secrets via `sync: false`; `healthCheckPath: /health` | Member 3 (spec), Member 5 (deploy) |
| `requirements.txt` | Pinned `fastapi`, `uvicorn[standard]`, `psycopg[binary,pool]` | Member 3 |

**Deferred to Member 5 (DevOps), not yet created:** `.dockerignore`,
`.env.example` (explicitly Member 5's file per `role-ownership.md` §1), and the
schema migration with the `app_runtime`/`ingest_admin` grants. The migration is
a guarded `migrations/**` write that needs a reviewer + rollback plan; the
application currently runs on in-memory stores, so it is not required to hold
the server. The grant model remains specified in this ADR and must be authored
before the runtime touches a real database (INV-SEC-001).

The image was validated locally by booting `python -m src.backend.main` on an
injected `PORT` and serving `/health` 200. A container build cannot be run in
the current sandbox (no container runtime); the first real build occurs on the
Render deploy and is owned by Member 5.

## Dependencies introduced

Per `architecture-blueprint.md` §10 ("new dependency -> ADR required"), this
decision introduces the HTTP framework and server used by the Render web service:

| Package | Pinned | Why | Verified |
|---|---|---|---|
| `fastapi` | 0.162.0 | HTTP boundary for the AppEntry routers; Pydantic request/response models | Imported and exercised in a real ASGI/TestClient run |
| `uvicorn[standard]` | 0.54.0 | ASGI server bound to the Render `PORT` | Booted and served `/health` on an injected port |
| `psycopg[binary,pool]` | 3.3.8 | Synchronous PostgreSQL driver + connection pool for the `users`/`sessions`/`user_vocabulary`/`learning_events` repositories (ADR-008, ADR-009, INV-PROG-001). Kept synchronous to match the existing service layer and avoid a destabilising async refactor. | Imported and compiled against the Python runtime; repositories use `dict_row` + `ON CONFLICT` idempotency |

They are declared in `requirements.txt` at the repository root. No other new
third-party package is introduced by this ADR. The safety boundary
(`src/backend/safety_boundary/**`) remains stdlib-only per `.agent/rules.md` §2
and `structural-constraints.md` C4.

## Alternatives considered
| Option | Why rejected |
|---|---|
| Render Free, single DB role with full grants | Fails INV-SEC-001: the runtime could write the corpus; the invariant could not be proven by a grant |
| Render Paid Starter | Meets p95 without cold start, but adds recurring cost the team budget does not cover at R1; reconsider if the cold-start review trigger fires |
| Split services on Render (separate retrieval service) | Rejected by ADR-001 C2: a cross-process retrieval contract cannot be proven offline without drift |
| Other PaaS (Fly.io, Railway) | Viable but not evaluated against the same criteria here; a topology change requires a new ADR and re-running the review triggers |

## Done-when checks for this ADR

- [ ] The Render service and PostgreSQL instance are provisioned and documented in the runtime policy catalog (RP-018).
- [ ] The `app_runtime` read-only grant is verified by `test/offline/test_database/test_vector_permissions.py::test_runtime_vector_read_only` on a real instance (live tier).
- [ ] `/health` and `/ready` are wired and Render health checks target `/health`.
- [ ] The daily AI cap is stored in PostgreSQL and survives a process restart (`RP-008`, `RP-018`).
- [ ] A rollback to the previous deploy is demonstrated and recorded in the logbook.

## Change log

| Date | Change | Evidence |
|---|---|---|
| 2026-11-06 | Proposed for R1: Render web service + managed pgvector, split DB roles, Free tier, `PORT` key | This ADR |
| 2026-11-06 | Accepted by human supervisor (Member 3) | Session approval; see `evaluation-logbook.md` L-014 |
