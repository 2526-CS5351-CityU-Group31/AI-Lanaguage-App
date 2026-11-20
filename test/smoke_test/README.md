# Live Smoke Test

A standalone, self-cleaning end-to-end smoke test for the AI-Companion backend.
It runs against a **live server over HTTP** (Render prod or a local instance) so
it exercises the real network, database, scope guard, and (when configured) the
LLM + grounded retrieval — things `test/offline/` deliberately does not.

> This directory is **not** the QA suite. `test/offline/` is owned by the QA
> lane (Member 5). This is a quick demo/handoff sanity check.

## Requirements

- Python 3.10+ (standard library only — no extra dependencies).
- Network access to the target server.

## Usage

```bash
# Against the live Render deployment (default):
python3 test/smoke_test/run_smoke_test.py

# Against a local server (e.g. `python -m src.backend.main` on port 8000):
python3 test/smoke_test/run_smoke_test.py --base-url http://127.0.0.1:8000

# Also verify rate limiting (HTTP 429 + Retry-After) as an extra final step:
python3 test/smoke_test/run_smoke_test.py --test-rate-limit

# Run ONLY the 3 boundary/security checks (skips the full lifecycle):
python3 test/smoke_test/run_smoke_test.py --security-only
```

Output is an aligned pass/fail table with HTTP status and latency per check.
The script exits `0` if every check passes, `1` otherwise. It never prints
passwords or session tokens, and it creates a throwaway user each run.

> `--test-rate-limit` is **off by default**. When enabled it runs **last**, after
> logout, and sends a rapid burst from a **fresh throwaway token** (its own
> per-token rate bucket), so it cannot lock out the primary smoke run or other
> clients. It passes only if the server returns **HTTP 429 with a `Retry-After`
> header**. Expect this step to take several seconds.

> Render Free instances sleep when idle — the first request may take ~30-50s
> (cold start). The script's timeout (120s) accommodates this.

## What it checks

1. **Health & CORS** — `GET /health` 200, `GET /ready` 200, `OPTIONS /sessions`
   with `Origin: http://localhost:5173` returns `Access-Control-Allow-Origin`.
2. **Auth & validation** — invalid CEFR (`C1`) and non-English (`fr`) register →
   422; valid register; login; `GET /me` without a token → 401.
3. **Profile** — `GET /me` 200; `PATCH /me` (CEFR + goals) 200.
4. **Vocabulary & progress** — `GET /vocabulary/random` 200 (grabs an
   `entry_id`); `POST /me/vocabulary/{entry_id}` 200; `GET /me/progress` shows
   the recorded vocabulary/mastery.
5. **Chat, grounded RAG & scope guard** — `POST /sessions` then messages:
   - `grammar_question` "What is the present simple tense?" → 200,
     `scope_status=accepted`, `abstained=false`, non-empty `source_ids`
     (grounded retrieval + citation validation).
   - `conversation_practice` "Help me practise English conversation about
     travel" → 200, `scope_status=accepted`, non-empty `answer`.
   - off-topic "Write a Python script to scrape a website" → 200,
     `scope_status=rejected` (scope guard blocks non-language-learning input).
6. **Logout** — `POST /auth/logout` succeeds; the old token then gets 401.
7. **Rate limiting (optional, `--test-rate-limit`)** — after logout, a rapid
   burst from a throwaway token must yield **HTTP 429 + `Retry-After`**. Off by
   default; runs last so normal runs are never rate-limited.

### Boundary/security checks (`--security-only`)

Run these alone with `--security-only` (also appended as extra checks at the end
of a normal run). Each creates throwaway users and prints no secrets:

- **Cross-user isolation (INV-AUTH-001)** — User B's token posting to User A's
  `session_id` → **403/404** (access denied).
- **ScopeGuard uncertain** — an ambiguous prompt (e.g. `"help"`) →
  **`scope_status == "uncertain"`** with a non-empty `scope_message`.
- **Disallowed CORS origin** — `OPTIONS /sessions` with
  `Origin: https://evil-example.com` must **not** echo that origin in
  `Access-Control-Allow-Origin`.

## Notes

- Grounded (`grammar_question`) checks require the lesson corpus to be ingested
  (`content_chunks` with `review_status='published'`) and `LLM_API_KEY` set on
  the server. If those are absent the answer abstains and the grounding check
  will report `FAIL` — that reflects server state, not a test bug.
- The script is read-only in spirit: it only creates one throwaway user (and its
  chat session / vocabulary row) per run. It does not clean up server-side data.
