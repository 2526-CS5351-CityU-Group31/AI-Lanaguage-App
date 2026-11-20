#!/usr/bin/env python3
"""Standalone live end-to-end smoke test for the AI-Companion backend.

This is NOT part of the QA lane (``test/offline/``). It exercises a *running*
server (Render prod or a local instance) over HTTP using only the standard
library, so it needs no extra dependencies and makes real network calls.

It is a fast, self-cleaning check for demos and handoffs. It never prints
passwords or session tokens.

Usage:
    python3 smoke_test/run_smoke_test.py
    python3 smoke_test/run_smoke_test.py --base-url http://127.0.0.1:8000

Exit code: 0 if every check passes, 1 otherwise.

Implements (verified behaviour, not enforced here): FR-AUTH-001, FR-PROF-001,
FR-VOC-001/002, FR-CHAT-001, FR-RAG-001; INV-SCOPE-001/002/003/004,
INV-AUTH-001, INV-LANG-001, INV-CEFR-001, INV-PROG-001, INV-CITE-001.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
import uuid

DEFAULT_BASE_URL = "https://ai-lanaguage-app.onrender.com"
LOCALHOST_ORIGIN = "http://localhost:5173"
REQUEST_TIMEOUT = 120.0

FIXED_REFUSAL = "I'm sorry, but I can only help with language-learning questions."


class Result:
    """One smoke check outcome."""

    def __init__(self, name: str, ok: bool, status: object, latency_ms: float, note: str = "") -> None:
        self.name = name
        self.ok = ok
        self.status = status
        self.latency_ms = latency_ms
        self.note = note


def _request(
    method: str,
    url: str,
    *,
    body: dict | None = None,
    token: str | None = None,
    origin: str | None = None,
    extra_headers: dict | None = None,
) -> tuple[int, dict, dict, float]:
    """Perform one HTTP request. Returns (status, headers, json_body, latency_ms)."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if origin:
        headers["Origin"] = origin
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    started = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            raw = resp.read()
            status = resp.getcode()
            resp_headers = {k.lower(): v for k, v in resp.headers.items()}
    except urllib.error.HTTPError as exc:
        raw = exc.read() or b""
        status = exc.code
        resp_headers = {k.lower(): v for k, v in exc.headers.items()} if exc.headers else {}
    latency_ms = (time.monotonic() - started) * 1000.0
    parsed: dict = {}
    if raw:
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            parsed = {}
    return status, resp_headers, parsed, latency_ms


def run(base_url: str, *, test_rate_limit: bool = False) -> list[Result]:
    """Run every lifecycle check and return the collected results.

    When ``test_rate_limit`` is True, a final burst step runs after logout to
    verify HTTP 429 + Retry-After. It uses a FRESH throwaway token so the burst
    is keyed to its own per-token bucket and cannot lock out normal runs or the
    primary smoke user. It is off by default.
    """
    results: list[Result] = []
    base = base_url.rstrip("/")
    email = f"smoke_{uuid.uuid4().hex[:12]}@example.com"
    password = "smoke-pass-123"

    def record(name: str, ok: bool, status: object, latency_ms: float, note: str = "") -> None:
        results.append(Result(name, ok, status, latency_ms, note))

    # ---- 1. Health & CORS -------------------------------------------------
    st, _, body, ms = _request("GET", f"{base}/health")
    record("GET /health", st == 200 and body.get("status") == "ok", st, ms)

    st, _, body, ms = _request("GET", f"{base}/ready")
    record("GET /ready", st == 200, st, ms)

    st, hdr, _, ms = _request(
        "OPTIONS",
        f"{base}/sessions",
        origin=LOCALHOST_ORIGIN,
        extra_headers={
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    acao = hdr.get("access-control-allow-origin")
    record(
        "OPTIONS /sessions (CORS)",
        st in (200, 204) and acao == LOCALHOST_ORIGIN,
        st,
        ms,
        note=f"ACAO={acao}",
    )

    # ---- 2. Auth & Validation --------------------------------------------
    st, _, _, ms = _request(
        "POST",
        f"{base}/auth/register",
        body={"email": f"bad_{uuid.uuid4().hex[:8]}@example.com", "password": password, "cefr_level": "C1", "language": "en"},
    )
    record("Register invalid CEFR -> 422", st == 422, st, ms)

    st, _, _, ms = _request(
        "POST",
        f"{base}/auth/register",
        body={"email": f"bad_{uuid.uuid4().hex[:8]}@example.com", "password": password, "cefr_level": "A2", "language": "fr"},
    )
    record("Register non-English -> 422", st == 422, st, ms)

    st, _, body, ms = _request(
        "POST",
        f"{base}/auth/register",
        body={"email": email, "password": password, "cefr_level": "A2", "language": "en"},
    )
    token = body.get("session_token", "")
    record("Register valid", st in (200, 201) and bool(token), st, ms)

    st, _, body, ms = _request("POST", f"{base}/auth/login", body={"email": email, "password": password})
    login_token = body.get("session_token", "")
    record("Login", st == 200 and bool(login_token), st, ms)
    if login_token:
        token = login_token

    st, _, _, ms = _request("GET", f"{base}/me")
    record("GET /me without token -> 401", st == 401, st, ms)

    # ---- 3. Profile -------------------------------------------------------
    st, _, body, ms = _request("GET", f"{base}/me", token=token)
    record("GET /me (auth)", st == 200 and body.get("email") == email, st, ms)

    st, _, body, ms = _request(
        "PATCH",
        f"{base}/me",
        body={"cefr_level": "B1", "learning_goals": "travel"},
        token=token,
    )
    record("PATCH /me", st == 200 and body.get("cefr_level") == "B1", st, ms)

    # ---- 4. Vocabulary & Progress ----------------------------------------
    st, _, body, ms = _request("GET", f"{base}/vocabulary/random?level=A1&count=3&seed=7")
    cards = body if isinstance(body, list) else []
    entry_id = cards[0].get("entry_id") if cards else None
    record("GET /vocabulary/random", st == 200 and bool(entry_id), st, ms, note=f"entry_id={entry_id}")

    if entry_id:
        st, _, _, ms = _request(
            "POST", f"{base}/me/vocabulary/{entry_id}", body={"state": "mastered"}, token=token
        )
        record("POST /me/vocabulary/{id}", st == 200, st, ms)
    else:
        record("POST /me/vocabulary/{id}", False, "skip", 0.0, note="no entry_id from dataset")

    st, _, body, ms = _request("GET", f"{base}/me/progress", token=token)
    words = body.get("words_reviewed", 0) if isinstance(body, dict) else 0
    mastered = body.get("mastered_vocabulary", 0) if isinstance(body, dict) else 0
    record(
        "GET /me/progress (recorded)",
        st == 200 and (words >= 1 or mastered >= 1),
        st,
        ms,
        note=f"words_reviewed={words}, mastered={mastered}",
    )

    # ---- 5. Chat, Grounded RAG & ScopeGuard ------------------------------
    st, _, body, ms = _request("POST", f"{base}/sessions", token=token)
    session_id = body.get("session_id") if isinstance(body, dict) else None
    record("POST /sessions", st in (200, 201) and bool(session_id), st, ms)

    def send(mode: str, message: str, rid: str) -> tuple[int, dict, float]:
        return _request(
            "POST",
            f"{base}/sessions/{session_id}/messages",
            body={"learner_mode": mode, "message": message, "request_id": rid},
            token=token,
        )

    if session_id:
        st, _, body, ms = send("grammar_question", "What is the present simple tense?", "smoke_gram")
        record(
            "grammar_question (grounded)",
            st == 200
            and body.get("scope_status") == "accepted"
            and body.get("abstained") is False
            and len(body.get("source_ids", [])) > 0,
            st,
            ms,
            note=f"source_ids={len(body.get('source_ids', []))}",
        )

        st, _, body, ms = send(
            "conversation_practice", "Help me practise English conversation about travel", "smoke_conv"
        )
        record(
            "conversation_practice",
            st == 200 and body.get("scope_status") == "accepted" and bool(body.get("answer")),
            st,
            ms,
        )

        st, _, body, ms = send(
            "text", "Write a Python script to scrape a website", "smoke_off"
        )
        record(
            "off-topic/coding guard (rejected)",
            st == 200 and body.get("scope_status") == "rejected",
            st,
            ms,
            note=f"scope_status={body.get('scope_status')}",
        )
    else:
        record("grammar_question (grounded)", False, "skip", 0.0, note="no session_id")
        record("conversation_practice", False, "skip", 0.0, note="no session_id")
        record("off-topic/coding guard (rejected)", False, "skip", 0.0, note="no session_id")

    # ---- 6. Logout --------------------------------------------------------
    st, _, _, ms = _request("POST", f"{base}/auth/logout", token=token)
    record("POST /auth/logout", st in (200, 204), st, ms)

    st, _, _, ms = _request("GET", f"{base}/me", token=token)
    record("GET /me after logout -> 401", st == 401, st, ms)

    # ---- 7. Optional rate-limit burst (last; off by default) -------------
    if test_rate_limit:
        # Fresh throwaway user -> its token is a separate rate-limit bucket, so
        # the burst cannot affect the primary smoke user or other clients.
        burst_email = f"rl_{uuid.uuid4().hex[:12]}@example.com"
        st, _, rl_body, ms = _request(
            "POST",
            f"{base}/auth/register",
            body={"email": burst_email, "password": password, "cefr_level": "A2", "language": "en"},
        )
        burst_token = rl_body.get("session_token", "") if isinstance(rl_body, dict) else ""
        if not burst_token:
            record("Rate limit 429 + Retry-After", False, st, ms, note="no burst token")
        else:
            target = f"{base}/me"  # authenticated, non-exempt endpoint
            got_429 = False
            retry_after = None
            last_status = None
            # Default server limit is 60/min; burst well past it (server may be
            # configured lower). 80 requests guarantees the window overflows.
            burst_started = time.monotonic()
            for _ in range(80):
                last_status, hdr, _, _ = _request("GET", target, token=burst_token)
                if last_status == 429:
                    got_429 = True
                    retry_after = hdr.get("retry-after")
                    break
            burst_ms = (time.monotonic() - burst_started) * 1000.0
            ok = got_429 and retry_after is not None
            note = f"Retry-After={retry_after}" if retry_after else "429 not reached"
            record("Rate limit 429 + Retry-After", ok, last_status, burst_ms, note=note)

    return results


def print_table(results: list[Result]) -> None:
    """Print a clean aligned pass/fail summary table."""
    name_w = max((len(r.name) for r in results), default=10)
    name_w = max(name_w, 28)
    header = f"{'CHECK':<{name_w}}  {'STATUS':>6}  {'LATENCY':>9}  {'RESULT':<6}  NOTE"
    print()
    print(header)
    print("-" * len(header))
    for r in results:
        status = str(r.status)
        latency = f"{r.latency_ms:8.0f}ms" if r.latency_ms else "       -"
        verdict = "PASS" if r.ok else "FAIL"
        print(f"{r.name:<{name_w}}  {status:>6}  {latency:>9}  {verdict:<6}  {r.note}")
    passed = sum(1 for r in results if r.ok)
    total = len(results)
    print("-" * len(header))
    print(f"{'TOTAL':<{name_w}}  {'':>6}  {'':>9}  {passed}/{total} passed")
    print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Live end-to-end smoke test for the backend API.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Server base URL")
    parser.add_argument(
        "--test-rate-limit",
        action="store_true",
        default=False,
        help="Also verify rate limiting (HTTP 429 + Retry-After). Runs last; "
        "sends a rapid burst from a throwaway token. Off by default.",
    )
    args = parser.parse_args(argv)

    print(f"Smoke testing backend at: {args.base_url}")
    if args.test_rate_limit:
        print("Rate-limit burst enabled (runs last, isolated throwaway token).")
    try:
        results = run(args.base_url, test_rate_limit=args.test_rate_limit)
    except Exception as exc:  # pragma: no cover - network failure path
        print(f"SMOKE TEST ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print_table(results)
    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
