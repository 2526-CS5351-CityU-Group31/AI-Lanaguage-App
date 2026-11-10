"""Check core machine-readable permission contracts against the permission model.

Implements the canonical command:
    python scripts/check_permissions.py

Scope (baseline R1): the default-deny posture, the three declared roles, and the
human-only authority modules are not auto-editable. Full path-by-path
isomorphism between the table and the config remains tracked as DBT-004.
"""

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PERMISSIONS_JSONC_PATH = REPO_ROOT / ".opencode" / "permissions.jsonc"

ROLE_NAMES = ("plan_agent", "build_agent", "verify_agent")

# Human-only authority modules (permission-model section 2).
AUTHORITY_MODULES = (
    "src/backend/safety_boundary/scope_guard.py",
    "src/backend/safety_boundary/citation_validator.py",
    "src/backend/auth/security.py",
)


def strip_jsonc_comments(text):
    """Remove // comments that appear outside double-quoted strings."""
    out = []
    in_string = False
    i = 0
    while i < len(text):
        ch = text[i]
        if in_string:
            out.append(ch)
            if ch == "\\" and i + 1 < len(text):
                out.append(text[i + 1])
                i += 2
                continue
            if ch == '"':
                in_string = False
            i += 1
        else:
            if ch == '"':
                in_string = True
                out.append(ch)
                i += 1
            elif ch == "/" and i + 1 < len(text) and text[i + 1] == "/":
                while i < len(text) and text[i] != "\n":
                    i += 1
            else:
                out.append(ch)
                i += 1
    return "".join(out)


def glob_to_regex(pattern):
    """Translate a simple glob (**, *, literals) into a regex."""
    out = []
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == "*":
            if i + 1 < len(pattern) and pattern[i + 1] == "*":
                out.append(".*")
                i += 2
            else:
                out.append("[^/]*")
                i += 1
        else:
            out.append(re.escape(ch))
            i += 1
    return re.compile("^" + "".join(out) + "$")


def matches(path, patterns):
    return any(glob_to_regex(p).match(path) for p in patterns)


def main() -> int:
    with PERMISSIONS_JSONC_PATH.open("r", encoding="utf-8") as f:
        config = json.loads(strip_jsonc_comments(f.read()))

    errors = []

    # 1. Default-deny posture.
    if config["permission"]["read"].get("*") != "deny":
        errors.append("permission.read is missing default '*': deny")
    if config["permission"]["edit"].get("*") != "deny":
        errors.append("permission.edit is missing default '*': deny")

    # 2. The three roles exist with read and write lists.
    roles = config["roles"]
    for role in ROLE_NAMES:
        if role not in roles:
            errors.append(f"role {role} is missing from permissions.jsonc")
            continue
        if not roles[role].get("read"):
            errors.append(f"role {role} has no read list")
        if not roles[role].get("write"):
            errors.append(f"role {role} has no write list")

    # 3. Authority modules must not be auto-editable (no matching "allow" rule).
    edit_rules = config["permission"]["edit"]
    for module in AUTHORITY_MODULES:
        matched = [
            value
            for pattern, value in edit_rules.items()
            if pattern != "*" and matches(module, [pattern])
        ]
        if "allow" in matched:
            errors.append(
                f"{module} is auto-editable; it must require human approval"
            )
        if not matched:
            errors.append(f"{module} has no explicit edit rule")

    if errors:
        for error in errors:
            print(f"check_permissions: {error}", file=sys.stderr)
        return 1

    print(
        "check_permissions: passed; default-deny set, 3 roles present, "
        "authority modules are human-gated."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
