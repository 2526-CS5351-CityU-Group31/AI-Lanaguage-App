# Configuration governance - baseline R1

**Purpose:** define every environment variable, its config key, type, default, validation and precedence; make invalid configuration fail loudly at startup; and keep `os.environ` out of every module except the config module.
**Owner:** Member 3 (Backend & Data); reviewed by Member 5.
**Related:** `structural-constraints.md` S5, ADR-006, ADR-007, ADR-009, `runtime-policy-catalog.md` RP-004/RP-008/RP-011/RP-013/RP-017.

## 1. Precedence

Later sources override earlier ones:

```
defaults  <  config/{ENVIRONMENT}.yaml  <  environment variables  <  CLI flags (scripts only)
```

- Environment overrides the file so a deployment can replace a baked-in default without rebuilding; a secret still may come only from an environment variable or a secret store, never from the YAML file or a CLI flag.
- A runtime service reads the environment at startup and then freezes it; there is no hot reload and no per-request `os.environ` lookup.
- Scripts (`scripts/*.py`) may accept CLI overrides for `--environment` and `--dry-run`; they may not accept a secret on the command line.

## 2. Key table

`Required` means the key must be present and valid for the stated environment; a missing value fails startup. `S` marks a secret: it is never logged, echoed or written to a report.

| Env var | Config key | Type | Default | Validation | Required | S |
|---|---|---|---|---|---|---|
| `ENVIRONMENT` | `environment` | enum `dev` `test` `prod` | none | must be one of the three; unknown fails | yes | no |
| `DATABASE_URL` | `database_url` | DSN string | none | scheme `postgresql://`; host and database present; connection probe at startup | yes | **S** |
| `SESSION_SECRET` | `session_secret` | string | none | >= 32 bytes; not a known placeholder | yes | **S** |
| `LLM_MODE` | `llm_mode` | enum `stub` `live` | `stub` in dev/test; none in prod | prod must be `live`; test may be `stub`; live requires key/model | yes | no |
| `LLM_API_KEY` | `llm_api_key` | string | none | non-empty when `llm_mode=live`; never logged | if live | **S** |
| `LLM_MODEL` | `llm_model` | string | none | allowlist of pinned ids; reject `latest`, `*`, empty | if live | no |
| `EMBEDDING_MODEL` | `embedding_model` | string | none | allowlist; must match the active index metadata | yes | no |
| `EMBEDDING_DIM` | `embedding_dim` | int | none | 1..4096; must match the active index dimension | yes | no |
| `PROMPT_VERSION` | `prompt_version` | string | `prompt_v1.0.0` | must match a file in `prompts/`; format `prompt_vX.Y.Z` | yes | no |
| `MAX_AI_CALLS_PER_DAY` | `max_ai_calls_per_day` | int | `50` | 1..1000 | yes | no |
| `CONTEXT_TOKEN_BUDGET` | `context_token_budget` | int | `1500` | 1000..4000; the per-turn prompt-token ceiling (`NFR-COST-001`) | yes | no |
| `COMPACTION_MESSAGE_LIMIT` | `compaction_message_limit` | int | `6` | 4..20; history older than this many messages is compacted (`NFR-COST-001`) | yes | no |
| `RETRIEVAL_TOP_K` | `retrieval_top_k` | int | `5` | 1..10 | yes | no |
| `RETRIEVAL_MIN_SCORE` | `retrieval_min_score` | float | `0.35` | 0.0..1.0 | yes | no |
| `RETRIEVAL_TIMEOUT_MS` | `retrieval_timeout_ms` | int | `2000` | 200..5000 | yes | no |
| `LLM_TIMEOUT_MS` | `llm_timeout_ms` | int | `25000` | 5000..60000; must exceed retrieval timeout + 5 s | yes | no |
| `RETRY_MAX` | `retry_max` | int | `2` | 0..3 | yes | no |
| `CIRCUIT_FAILURE_THRESHOLD` | `circuit_failure_threshold` | int | `3` | 1..10 | yes | no |
| `CIRCUIT_RESET_SECONDS` | `circuit_reset_seconds` | int | `300` | 30..900 | yes | no |
| `MAX_INPUT_CHARS` | `max_input_chars` | int | `1500` | 100..4000 | yes | no |
| `RATE_LIMIT_PER_MINUTE` | `rate_limit_per_minute` | int | `60` | 1..600 | yes | no |
| `CORS_ALLOWED_ORIGINS` | `cors_allowed_origins` | comma list | `http://localhost:5173` in dev; none in prod | prod entries must be `https://` and exact; no `*` | yes | no |
| `LOG_LEVEL` | `log_level` | enum `debug` `info` `warn` `error` | `info` | prod may not be `debug` | yes | no |
| `FEATURE_AI_PAUSED` | `feature_ai_paused` | bool | `false` | true/false/1/0; when true, AI endpoints return 503 except health | no | no |
| `PORT` | `port` | int | `8000` | 1..65535; Render injects it; read only by the config module so S5 holds | no | no |

### Mapping rules

- One env var maps to exactly one config key; no aliases and no underscore/case variants.
- The config module is the only module that calls `os.environ` or reads a dotenv file.
- `.env.example` lists names and safe placeholders only; it never contains a real key.
- A new key requires: this table, `config/{env}.yaml` documentation if applicable, the config object field + validation, a startup test, and an ADR if the key changes behaviour or a default.

## 3. Fail-loud rule

Validation runs once at startup, before the server binds a port. All errors are collected, printed **without values**, and the process exits with code **78** (`EX_CONFIG`). There is no "start with defaults and warn" path.

```
$ python -m src.backend.main
FATAL config: 2 invalid keys (ENVIRONMENT=prod)
  - DATABASE_URL: required when ENVIRONMENT=prod
  - MAX_AI_CALLS_PER_DAY: 0 outside [1, 1000]
Exit code: 78
```

Rules:

1. A missing required key is fatal; it is never replaced by an empty string or a default.
2. A secret with a placeholder value (`changeme`, `test`, `xxx`) is fatal in `prod`.
3. Validation errors name the key and the rule, never the value; a secret is never printed.
4. The startup check includes a database connection probe and an index-dimension probe; a mismatch is fatal, not a warning.
5. Tests assert exit code 78 for at least: missing database URL, missing session secret, invalid enum, out-of-range int, mismatched embedding dimension.

## 4. Immutability after initialisation

- The config object is a frozen dataclass; mutation raises `FrozenInstanceError`.
- A test asserts that a runtime request cannot change a config value.
- Services receive the config object by dependency injection; none constructs its own config.
- A change requires a process restart and a new deploy record; there is no runtime setter.
- `FEATURE_AI_PAUSED` is read at request time from a frozen value; toggling it requires a restart by an operator, not an agent.

## 5. No `os.environ` outside the config module

This is structural constraint S5 and is enforced by two checks:

```bash
grep -rn "os\.environ\|os\.getenv\|load_dotenv" src --include='*.py' | grep -v 'config.py:'
# expected: no output; exit 1 is the pass condition for grep
```

`test/structural/test_config_boundary.py` also walks the AST to reject `os.environ`, `os.getenv` and `dotenv` imports outside the config module. A violation fails Tier 1, not a review comment.

## 6. Configuration and runtime policies

| Policy | Config keys it reads | Rule |
|---|---|---|
| RP-004 model unavailable | `llm_timeout_ms`, `retry_max`, `circuit_failure_threshold`, `circuit_reset_seconds` | Bounds are config, not code constants |
| RP-006 retrieval unavailable | `retrieval_timeout_ms`, `retrieval_top_k`, `retrieval_min_score` | A timeout triggers abstention, not an unbounded wait |
| RP-008 daily cap | `max_ai_calls_per_day` | Cap is per user per 24 h; a restart does not reset the counter |
| RP-011 database unavailable | `database_url` | A failed readiness probe yields 503; no partial record |
| RP-013 cost drift | `context_token_budget`, `compaction_message_limit` | Drift alert uses the per-turn token budget as the anchor |
| RP-017 token budget | `context_token_budget`, `compaction_message_limit` | Prompt over the ceiling is compacted, then the over-long input is rejected (422) |
| ADR-005 response caps | `max_input_chars`, `retrieval_top_k` | Input cap is rejected before a model call (422) |

## 7. Done-when status

- [x] Every key has a type, default (or "none"), validation and a consumer.
- [x] The fail-loud rule has a concrete startup example and an exit code.
- [x] `os.environ` is confined to the config module with a grep and AST check.
- [ ] Config startup tests exist and fail on each invalid case (`DBT-003`).
- [ ] The precedence test exists (default < file < env < CLI) (`DBT-003`).
- [ ] A secret is proven absent from logs and error output by a sampling test (`DBT-003`).
