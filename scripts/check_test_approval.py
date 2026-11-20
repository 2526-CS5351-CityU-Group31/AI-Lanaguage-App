"""Gate 1 - test approval precedes implementation.

Implements: ADR-010 G1; `verification-constraints.md` VS-18 and §7;
`docs/code-governance/ci-gates-design.md` Part A.

Canonical command:
    python scripts/check_test_approval.py --pr <number> [--base origin/main]

The gate proves the *order* "approval before implementation". A human commits
`docs/code-governance/approvals/PR-<number>.yaml` before any commit on the PR
branch that touches `src/`, `prompts/` or `migrations/`.

Pass condition (VS-18): 0 implementation commits without a prior approval.

Exit 0 with a one-line summary, or exit 1 with exactly one typed code:

    APPROVAL_MISSING              no artifact for this PR
    APPROVAL_MALFORMED            artifact unreadable, or a required field absent/invalid
    SELF_APPROVAL                 the approver authored an implementation commit
    APPROVAL_AFTER_IMPLEMENTATION `approved_at` is later than the first implementation commit
    REQUIREMENT_UNKNOWN           a requirement id is not in docs/req/requirements.yaml
    REQUIREMENTS_MISSING          docs/req/requirements.yaml is absent or unreadable
    BASE_REF_MISSING              the base ref cannot be resolved
    GIT_UNAVAILABLE               git is not installed or cannot be executed

`BASE_REF_MISSING` and `GIT_UNAVAILABLE` are not among the four codes named in
the design note; they exist so an unverifiable gate fails closed instead of
passing by accident.

Deliberately absent, per the design note: grandfathering of earlier PRs, identity
maps, and base-ref anti-gaming checks. The gate applies from the commit that
switches it on.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

APPROVAL_DIR = Path("docs") / "code-governance" / "approvals"
REQUIREMENTS_REL = Path("docs") / "req" / "requirements.yaml"

#: Commits touching these paths are "implementation" for the ordering check.
IMPLEMENTATION_PATHS: tuple[str, ...] = ("src", "prompts", "migrations")

#: Registry id shape from docs/req/req-schema.json.
REQUIREMENT_ID_PATTERN = re.compile(r"^(?:FR|NFR|INV)-[A-Z0-9]+-[0-9]{3}$")


class GateFailure(Exception):
    """A gate outcome carrying the typed code CI reports."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ImplementationCommit:
    """One commit that changed implementation paths."""

    sha: str
    committed_at: dt.datetime
    author_name: str
    author_email: str


@dataclass(frozen=True)
class Approval:
    """The validated contents of an approval artifact."""

    approver: str
    approved_at: dt.datetime
    requirement_ids: tuple[str, ...]
    tests: tuple[str, ...]
    rollback: str


def repo_root() -> Path:
    """Return the repository root, falling back to the script's parent directory."""
    fallback = Path(__file__).resolve().parent.parent
    result = _git(fallback, ["rev-parse", "--show-toplevel"], allow_failure=True)
    if result is not None and result.strip():
        return Path(result.strip())
    return fallback


def parse_timestamp(value: str, *, code: str, field: str) -> dt.datetime:
    """Parse an ISO 8601 timestamp; a naive value is read as UTC."""
    text = value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError as exc:
        raise GateFailure(code, f"{field} is not an ISO 8601 timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed


def _run_git(root: Path, args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    """Run git, mapping a missing binary to a typed gate failure."""
    try:
        return subprocess.run(
            ["git", *args],
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except (FileNotFoundError, OSError) as exc:
        raise GateFailure("GIT_UNAVAILABLE", f"git is required to run this gate: {exc}") from exc


def _git(root: Path, args: Sequence[str], *, allow_failure: bool = False) -> str | None:
    """Run git and return stdout; ``None`` means the command failed (if allowed)."""
    result = _run_git(root, args)
    if result.returncode != 0:
        if allow_failure:
            return None
        raise GateFailure(
            "BASE_REF_MISSING",
            f"git {' '.join(args)} failed: {result.stderr.strip() or result.stdout.strip()}",
        )
    return result.stdout


def resolve_base(root: Path, base: str) -> str:
    """Resolve the base ref, or fail closed."""
    if _git(root, ["rev-parse", "--verify", "--quiet", f"{base}^{{commit}}"], allow_failure=True) is None:
        raise GateFailure(
            "BASE_REF_MISSING",
            f"base ref {base!r} cannot be resolved; fetch the base branch "
            "(actions/checkout needs fetch-depth: 0) or pass --base",
        )
    return base


def implementation_commits(root: Path, base: str) -> list[ImplementationCommit]:
    """Return implementation commits in ``base..HEAD``, oldest first."""
    separator = "\x1f"
    fmt = separator.join(["%H", "%cI", "%an", "%ae"])
    output = _git(
        root,
        ["log", "--reverse", f"--format={fmt}", f"{base}..HEAD", "--", *IMPLEMENTATION_PATHS],
    )
    commits: list[ImplementationCommit] = []
    for line in (output or "").splitlines():
        if not line.strip():
            continue
        parts = line.split(separator)
        if len(parts) != 4:
            raise GateFailure("GIT_UNAVAILABLE", f"unexpected git log record: {line!r}")
        sha, committed_at, author_name, author_email = parts
        commits.append(
            ImplementationCommit(
                sha=sha,
                committed_at=parse_timestamp(
                    committed_at, code="GIT_UNAVAILABLE", field="commit date"
                ),
                author_name=author_name,
                author_email=author_email,
            )
        )
    return commits


def artifact_path(root: Path, pr: int) -> Path:
    """Return the approval artifact path for one PR."""
    return root / APPROVAL_DIR / f"PR-{pr}.yaml"


def load_artifact(path: Path, pr: int) -> Approval:
    """Load and validate the approval artifact; raise a typed failure on any gap."""
    if not path.is_file():
        raise GateFailure(
            "APPROVAL_MISSING",
            f"no approval artifact at {path.as_posix()}; a human must commit it before coding",
        )
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise GateFailure("APPROVAL_MALFORMED", f"{path.as_posix()} cannot be parsed: {exc}") from exc
    if not isinstance(raw, Mapping):
        raise GateFailure("APPROVAL_MALFORMED", f"{path.as_posix()} must be a YAML mapping")
    return _validate_artifact(raw, path, pr)


def _require_text(field: str, value: Any, path: Path, *, non_empty: bool = True) -> str:
    if not isinstance(value, str) or (non_empty and not value.strip()):
        raise GateFailure(
            "APPROVAL_MALFORMED", f"{path.as_posix()}: {field} must be a non-empty string"
        )
    return value.strip()


def _validate_artifact(raw: Mapping[str, Any], path: Path, pr: int) -> Approval:
    declared_pr = raw.get("pr")
    if declared_pr is not None:
        if isinstance(declared_pr, bool) or not isinstance(declared_pr, int) or declared_pr != pr:
            raise GateFailure(
                "APPROVAL_MALFORMED",
                f"{path.as_posix()}: pr must be {pr}, found {declared_pr!r}",
            )

    approver = _require_text("approver", raw.get("approver"), path)

    approved_at_raw = raw.get("approved_at")
    approved_at_text = _require_text("approved_at", approved_at_raw, path)
    approved_at = parse_timestamp(approved_at_text, code="APPROVAL_MALFORMED", field="approved_at")

    requirement_ids = _require_id_list(raw.get("requirement_ids"), path)

    tests_raw = raw.get("tests")
    if not isinstance(tests_raw, list) or not tests_raw:
        raise GateFailure(
            "APPROVAL_MALFORMED", f"{path.as_posix()}: tests must be a non-empty list"
        )
    tests = tuple(_test_name(entry, path, index) for index, entry in enumerate(tests_raw))

    rollback = _require_text("rollback", raw.get("rollback"), path)

    return Approval(
        approver=approver,
        approved_at=approved_at,
        requirement_ids=requirement_ids,
        tests=tests,
        rollback=rollback,
    )


def _require_id_list(value: Any, path: Path) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise GateFailure(
            "APPROVAL_MALFORMED",
            f"{path.as_posix()}: requirement_ids must be a non-empty list of FR/NFR/INV ids",
        )
    ids: list[str] = []
    for entry in value:
        if not isinstance(entry, str) or not REQUIREMENT_ID_PATTERN.match(entry.strip()):
            raise GateFailure(
                "APPROVAL_MALFORMED",
                f"{path.as_posix()}: {entry!r} is not a FR/NFR/INV requirement id",
            )
        ids.append(entry.strip())
    return tuple(ids)


def _test_name(entry: Any, path: Path, index: int) -> str:
    """Read the proposed-test name from a string or a ``{name, covers}`` mapping."""
    if isinstance(entry, str):
        name = entry.strip()
    elif isinstance(entry, Mapping):
        name = _require_text(f"tests[{index}].name", entry.get("name"), path)
    else:
        name = ""
    if not name:
        raise GateFailure(
            "APPROVAL_MALFORMED",
            f"{path.as_posix()}: tests[{index}] must name the proposed test",
        )
    # Proposed tests are approved *before* they exist; existence is not checked here.
    return name


def load_requirement_ids(path: Path) -> frozenset[str]:
    """Return the ids declared in the requirements registry."""
    if not path.is_file():
        raise GateFailure("REQUIREMENTS_MISSING", f"{path.as_posix()} does not exist")
    try:
        registry = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise GateFailure("REQUIREMENTS_MISSING", f"{path.as_posix()} cannot be parsed: {exc}") from exc
    if not isinstance(registry, Mapping):
        raise GateFailure("REQUIREMENTS_MISSING", f"{path.as_posix()} must be a YAML mapping")
    entries = registry.get("requirements")
    if not isinstance(entries, list):
        raise GateFailure("REQUIREMENTS_MISSING", f"{path.as_posix()} has no requirements list")
    ids = {
        str(entry["id"]).strip()
        for entry in entries
        if isinstance(entry, Mapping) and entry.get("id")
    }
    if not ids:
        raise GateFailure("REQUIREMENTS_MISSING", f"{path.as_posix()} declares no requirement ids")
    return frozenset(ids)


def _identity_candidates(approver: str) -> set[str]:
    """Normalised strings an approver name may match against a commit author."""
    normalised = approver.strip().casefold()
    candidates = {normalised}
    if "@" not in normalised:
        # "Adrian" against "adrian@example.com": the local part is the same person.
        candidates.add(normalised.replace(" ", "."))
    return candidates


def _author_matches(approver: str, commit: ImplementationCommit) -> bool:
    candidates = _identity_candidates(approver)
    name = commit.author_name.strip().casefold()
    email = commit.author_email.strip().casefold()
    local_part = email.split("@", 1)[0]
    return name in candidates or email in candidates or local_part in candidates


def check(pr: int, base: str, root: Path) -> tuple[str, Approval, list[ImplementationCommit]]:
    """Run the four checks and return the summary parts on success."""
    artifact = load_artifact(artifact_path(root, pr), pr)

    resolved_base = resolve_base(root, base)
    commits = implementation_commits(root, resolved_base)

    if commits:
        for commit in commits:
            if _author_matches(artifact.approver, commit):
                raise GateFailure(
                    "SELF_APPROVAL",
                    f"approver {artifact.approver!r} authored implementation commit "
                    f"{commit.sha[:12]} ({commit.committed_at.isoformat()}); "
                    "a different named human must approve",
                )
        first = commits[0]
        if artifact.approved_at > first.committed_at:
            raise GateFailure(
                "APPROVAL_AFTER_IMPLEMENTATION",
                f"approved_at {artifact.approved_at.isoformat()} is later than the first "
                f"implementation commit {first.sha[:12]} at {first.committed_at.isoformat()}",
            )

    known_ids = load_requirement_ids(root / REQUIREMENTS_REL)
    unknown = [rid for rid in artifact.requirement_ids if rid not in known_ids]
    if unknown:
        raise GateFailure(
            "REQUIREMENT_UNKNOWN",
            f"{', '.join(unknown)} not declared in {REQUIREMENTS_REL.as_posix()}",
        )

    if commits:
        summary = (
            f"PR #{pr} approved by {artifact.approver} at {artifact.approved_at.isoformat()}; "
            f"{len(commits)} implementation commit(s) in {resolved_base}..HEAD, "
            f"first at {commits[0].committed_at.isoformat()}"
        )
    else:
        summary = (
            f"PR #{pr} approved by {artifact.approver} at {artifact.approved_at.isoformat()}; "
            f"no implementation commits in {resolved_base}..HEAD"
        )
    return summary, artifact, commits


def _fail(code: str, message: str) -> int:
    print(f"check_test_approval: {code}: {message}", file=sys.stderr)
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print(f"::error title=Gate 1 ({code})::{message}")
    return 1


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Gate 1: verify a test-approval artifact predates implementation.",
    )
    parser.add_argument("--pr", type=int, required=True, help="pull request number")
    parser.add_argument(
        "--base",
        default="origin/main",
        help="base ref to diff against (default: origin/main)",
    )
    return parser.parse_args(list(argv))


def main(argv: Sequence[str]) -> int:
    args = _parse_args(argv)
    try:
        root = repo_root()
        summary, _approval, _commits = check(args.pr, args.base, root)
    except GateFailure as failure:
        return _fail(failure.code, failure.message)
    print(f"check_test_approval: passed; {summary}.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
