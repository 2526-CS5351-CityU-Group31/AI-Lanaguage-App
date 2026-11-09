"""Validate the requirements registry against its JSON schema and baseline rules.

Implements the canonical command:
    python scripts/validate_req.py docs/req/requirements.yaml

Pass condition (verification-constraints VS-01):
    exit 0; 31 requirements; 0 schema errors.
"""

import json
import sys
from pathlib import Path

import yaml
from jsonschema import ValidationError, validate

# Baseline R1: the registry must contain exactly 31 requirements.
EXPECTED_REQUIREMENT_COUNT = 31

# Schema location relative to this script: ../docs/req/req-schema.json
SCHEMA_PATH = Path(__file__).resolve().parent.parent / "docs" / "req" / "req-schema.json"


def main() -> int:
    if len(sys.argv) != 2:
        print(
            "Usage: python scripts/validate_req.py <requirements.yaml>",
            file=sys.stderr,
        )
        return 1

    registry_path = Path(sys.argv[1])

    try:
        with registry_path.open("r", encoding="utf-8") as f:
            registry = yaml.safe_load(f)
        with SCHEMA_PATH.open("r", encoding="utf-8") as f:
            schema = json.load(f)
    except (OSError, yaml.YAMLError, json.JSONDecodeError) as exc:
        print(f"validate_req: failed to read input files: {exc}", file=sys.stderr)
        return 1

    errors = []

    # 1. JSON Schema validation: required fields, enums, ID pattern, etc.
    try:
        validate(instance=registry, schema=schema)
    except ValidationError as exc:
        errors.append(f"schema violation: {exc.message}")

    requirements = (
        registry.get("requirements", []) if isinstance(registry, dict) else []
    )

    # 2. Requirement IDs must be unique.
    ids = [r.get("id") for r in requirements if isinstance(r, dict)]
    seen = set()
    duplicates = []
    for identifier in ids:
        if identifier in seen:
            if identifier not in duplicates:
                duplicates.append(identifier)
        else:
            seen.add(identifier)
    if duplicates:
        errors.append(f"duplicate requirement IDs: {', '.join(duplicates)}")

    # 3. Baseline requirement count.
    actual_count = len(requirements)
    if actual_count != EXPECTED_REQUIREMENT_COUNT:
        errors.append(
            f"requirement count {actual_count} does not match expected "
            f"{EXPECTED_REQUIREMENT_COUNT}"
        )

    if errors:
        for error in errors:
            print(f"validate_req: {error}", file=sys.stderr)
        print(f"validate_req: failed with {len(errors)} error(s).", file=sys.stderr)
        return 1

    print(
        f"validate_req: passed; {actual_count} requirements, 0 schema errors, "
        "0 duplicate IDs."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
