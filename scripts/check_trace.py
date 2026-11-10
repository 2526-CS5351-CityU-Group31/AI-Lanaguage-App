"""Check trace-matrix coverage against the requirements registry.

Implements the canonical command:
    python scripts/check_trace.py

Pass condition (verification-constraints VS-02):
    one row per requirement; 31/31; 0 orphans; 0 dead rows.
"""

import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS_PATH = REPO_ROOT / "docs" / "req" / "requirements.yaml"
TRACE_MATRIX_PATH = REPO_ROOT / "docs" / "architecture" / "trace-matrix.md"

# Column index of "Test / evidence" in the trace-matrix table.
EVIDENCE_COLUMN = 4

# A genuine trace row is keyed by a requirement ID with the schema pattern.
ID_PATTERN = re.compile(r"^(FR|NFR|INV)-[A-Z0-9]+-[0-9]{3}$")


def parse_matrix_rows(text):
    """Return the cells of the trace rows keyed by a requirement ID.

    The document also contains a separate summary table; matching the first
    column against the requirement ID pattern keeps only the real trace rows.
    """
    rows = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if cells and ID_PATTERN.match(cells[0]):
            rows.append(cells)
    return rows


def main() -> int:
    with REQUIREMENTS_PATH.open("r", encoding="utf-8") as f:
        registry = yaml.safe_load(f)
    with TRACE_MATRIX_PATH.open("r", encoding="utf-8") as f:
        matrix_text = f.read()

    requirement_ids = [req["id"] for req in registry["requirements"]]
    matrix_rows = parse_matrix_rows(matrix_text)
    matrix_ids = [row[0] for row in matrix_rows]

    errors = []

    requirement_set = set(requirement_ids)
    matrix_set = set(matrix_ids)

    orphans = sorted(requirement_set - matrix_set)
    dead = sorted(matrix_set - requirement_set)
    if orphans:
        errors.append(
            f"requirements without a trace row: {', '.join(orphans)}"
        )
    if dead:
        errors.append(f"trace rows without a requirement: {', '.join(dead)}")

    # Every row must name a non-empty test/evidence cell.
    for row in matrix_rows:
        req_id = row[0]
        evidence = row[EVIDENCE_COLUMN] if len(row) > EVIDENCE_COLUMN else ""
        if not evidence:
            errors.append(f"{req_id} has an empty Test/evidence cell")

    if len(matrix_ids) != len(requirement_ids):
        errors.append(
            f"trace rows {len(matrix_ids)} do not match requirements "
            f"{len(requirement_ids)}"
        )

    if errors:
        for error in errors:
            print(f"check_trace: {error}", file=sys.stderr)
        return 1

    print(
        f"check_trace: passed; {len(matrix_ids)}/{len(requirement_ids)} rows, "
        "0 orphans, 0 dead rows."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
