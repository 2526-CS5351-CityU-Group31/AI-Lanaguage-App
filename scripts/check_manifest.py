"""Check that every MCP tool has an ADR source, a requirement and one caller.

Implements the canonical command:
    python scripts/check_manifest.py

Pass condition (verification-constraints VS-08):
    every tool has an ADR, a requirement and exactly one caller; 0 unowned tools.
"""

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = REPO_ROOT / "docs" / "code-governance" / "mcp-tool-manifest.md"

# Tool tables have 11 columns.
EXPECTED_COLUMNS = 11

# Column indices in the tool tables.
TOOL = 0
ADR_SOURCE = 2
ALLOWED_CALLER = 3
REQUIREMENT = 5

ID_PATTERN = re.compile(r"^(FR|NFR|INV)-[A-Z0-9]+-[0-9]{3}$")
ID_IN_TEXT = re.compile(r"(?:FR|NFR|INV)-[A-Z0-9]+-[0-9]{3}")


def backtick_tokens(cell):
    return re.findall(r"`([^`]+)`", cell)


def parse_tool_rows(text):
    rows = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) != EXPECTED_COLUMNS:
            continue
        if all(cell and set(cell) <= set("-: ") for cell in cells):
            continue
        if cells[0] == "Tool":
            continue
        rows.append(cells)
    return rows


def main() -> int:
    with MANIFEST_PATH.open("r", encoding="utf-8") as f:
        manifest_text = f.read()

    tool_rows = parse_tool_rows(manifest_text)
    errors = []
    seen_tools = set()

    for cells in tool_rows:
        tool_names = backtick_tokens(cells[TOOL])
        tool_name = tool_names[0] if tool_names else cells[TOOL]

        if tool_name in seen_tools:
            errors.append(f"{tool_name}: tool is listed more than once")
        seen_tools.add(tool_name)

        # 1. ADR source must be present.
        if not cells[ADR_SOURCE] or "ADR" not in cells[ADR_SOURCE]:
            errors.append(f"{tool_name}: missing ADR source")

        # 2. Exactly one allowed caller.
        callers = backtick_tokens(cells[ALLOWED_CALLER])
        if len(callers) != 1:
            errors.append(
                f"{tool_name}: expected exactly one allowed caller, found "
                f"{len(callers)}"
            )

        # 3. At least one valid requirement ID.
        requirement_ids = ID_IN_TEXT.findall(cells[REQUIREMENT])
        if not requirement_ids:
            errors.append(f"{tool_name}: missing requirement")
        for identifier in requirement_ids:
            if not ID_PATTERN.match(identifier):
                errors.append(f"{tool_name}: invalid requirement ID {identifier}")

    if errors:
        for error in errors:
            print(f"check_manifest: {error}", file=sys.stderr)
        print(
            f"check_manifest: failed with {len(errors)} error(s).",
            file=sys.stderr,
        )
        return 1

    print(
        f"check_manifest: passed; {len(tool_rows)} tools, each with an ADR, "
        "one caller and a valid requirement; 0 unowned tools."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
