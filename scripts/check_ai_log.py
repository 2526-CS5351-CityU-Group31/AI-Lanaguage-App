"""Validate the AI-use log: schema, unique sessions and append-only history.

Implements the canonical command:
    python scripts/check_ai_log.py

Pass condition (verification-constraints VS-09):
    every session is schema-valid, session IDs are unique and no existing
    session is modified or removed; 0 invalid sessions.
"""

import json
import subprocess
import sys
from pathlib import Path

import yaml
from jsonschema import FormatChecker, validate

REPO_ROOT = Path(__file__).resolve().parent.parent
LOG_PATH = REPO_ROOT / "docs" / "code-governance" / "ai-use-log.yaml"
SCHEMA_PATH = REPO_ROOT / "docs" / "code-governance" / "ai-use-log-schema.json"
LOG_RELATIVE_PATH = "docs/code-governance/ai-use-log.yaml"


def load_base_log():
    """Return the log as it exists on the base branch, or None if unavailable."""
    for ref in ("origin/main", "main"):
        try:
            result = subprocess.run(
                ["git", "show", f"{ref}:{LOG_RELATIVE_PATH}"],
                capture_output=True,
                text=True,
                cwd=str(REPO_ROOT),
                check=True,
            )
        except (FileNotFoundError, subprocess.CalledProcessError):
            continue
        return yaml.safe_load(result.stdout)
    return None


def main() -> int:
    errors = []

    with SCHEMA_PATH.open("r", encoding="utf-8") as f:
        schema = json.load(f)
    with LOG_PATH.open("r", encoding="utf-8") as f:
        log_data = yaml.safe_load(f)

    # 1. Schema validation (including the date format).
    try:
        validate(instance=log_data, schema=schema, format_checker=FormatChecker())
    except Exception as exc:  # ValidationError
        errors.append(f"schema validation failed: {exc.message}")
        log_data = {"sessions": []}

    sessions = log_data.get("sessions", [])

    # 2. Unique session IDs.
    seen = set()
    for session in sessions:
        session_id = session.get("session_id", "<missing>")
        if session_id in seen:
            errors.append(f"{session_id}: duplicate session ID")
        seen.add(session_id)

    # 3. Append-only: existing sessions must be unchanged and still present.
    base_log = load_base_log()
    if base_log is not None:
        current = {session.get("session_id"): session for session in sessions}
        for base_session in base_log.get("sessions", []):
            session_id = base_session.get("session_id")
            if session_id not in current:
                errors.append(
                    f"{session_id}: session was removed; the log is append-only"
                )
            elif current[session_id] != base_session:
                errors.append(
                    f"{session_id}: existing session was modified; "
                    "the log is append-only"
                )

    if errors:
        for error in errors:
            print(f"check_ai_log: {error}", file=sys.stderr)
        return 1

    print(
        f"check_ai_log: passed; {len(sessions)} valid sessions, unique IDs, "
        "append-only history intact."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
