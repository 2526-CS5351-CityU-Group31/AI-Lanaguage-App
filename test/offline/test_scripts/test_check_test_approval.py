"""Gate 1 tests: `scripts/check_test_approval.py` against real temporary git repositories.

Implements: NFR-GOV-001; `verification-constraints.md` VS-18 and §8 item 14;
`docs/code-governance/ci-gates-design.md` §A.4.

Each test builds its own repository and commits, because the gate's whole claim is
about commit ordering: one variable moves at a time (artifact present/absent,
approver identity, approval time, requirement ids), while the implementation
commit stays fixed.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_REL = Path("scripts") / "check_test_approval.py"
REQUIREMENTS = REPO_ROOT / "docs" / "req" / "requirements.yaml"
ARTIFACT_REL = Path("docs") / "code-governance" / "approvals"

BASE_TIME = "2026-11-15T09:00:00+00:00"
APPROVAL_TIME = "2026-11-15T10:00:00+00:00"
LATE_APPROVAL_TIME = "2026-11-15T12:00:00+00:00"
IMPLEMENTATION_TIME = "2026-11-15T11:00:00+00:00"

APPROVER = ("Adrian", "adrian@example.com")
AUTHOR = ("Luming", "luming@example.com")

PROPOSED_TEST = "test/offline/test_safety_boundary/test_citation_validator.py::test_reject_invalid_citations"

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None,
    reason="git is required to build the fixture repositories",
)


def _git(
    repo: Path,
    *args: str,
    date: str | None = None,
    author: tuple[str, str] = AUTHOR,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run git in the fixture repository with a fixed identity and date."""
    env = os.environ.copy()
    if date is not None:
        env["GIT_AUTHOR_DATE"] = date
        env["GIT_COMMITTER_DATE"] = date
    command = ["git"]
    if args and args[0] == "commit":
        command += [
            "-c",
            f"user.name={author[0]}",
            "-c",
            f"user.email={author[1]}",
            "-c",
            "commit.gpgsign=false",
        ]
    command += list(args)
    return subprocess.run(
        command,
        cwd=str(repo),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=check,
    )


def _write(repo: Path, relative: str, text: str) -> None:
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _commit(repo: Path, message: str, *, date: str, author: tuple[str, str] = AUTHOR) -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", message, date=date, author=author)


def _artifact(
    *,
    pr: int | None = 7,
    approver: str = "Adrian",
    approved_at: str = APPROVAL_TIME,
    requirement_ids: list[str] | None = None,
    tests: list[object] | None = None,
    rollback: str | None = "Revert the branch.",
) -> str:
    """Render an approval artifact; ``None`` omits a field so the gate must reject it."""
    document: dict[str, object] = {}
    if pr is not None:
        document["pr"] = pr
    document["approver"] = approver
    document["approved_at"] = approved_at
    document["requirement_ids"] = (
        requirement_ids if requirement_ids is not None else ["NFR-GOV-001"]
    )
    document["tests"] = (
        tests if tests is not None else [{"name": PROPOSED_TEST, "covers": "INV-CITE-001"}]
    )
    if rollback is not None:
        document["rollback"] = rollback
    return yaml.safe_dump(document, sort_keys=False)


def _repo(tmp_path: Path) -> Path:
    """Create a fixture repository with the gate script, the registry and a base commit."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "--initial-branch=main")
    _write(repo, str(SCRIPT_REL), (REPO_ROOT / SCRIPT_REL).read_text(encoding="utf-8"))
    _write(
        repo,
        "docs/req/requirements.yaml",
        REQUIREMENTS.read_text(encoding="utf-8"),
    )
    _write(repo, "README.md", "fixture repository\n")
    _commit(repo, "baseline", date=BASE_TIME)
    _git(repo, "checkout", "-b", "feature")
    return repo


def _run_gate(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(repo / SCRIPT_REL), *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _assert_failure(result: subprocess.CompletedProcess[str], code: str) -> None:
    assert result.returncode == 1, result.stdout + result.stderr
    assert code in result.stderr, result.stdout + result.stderr


def test_valid_approval_before_implementation_passes(tmp_path: Path) -> None:
    """NFR-GOV-001 / VS-18: an approval committed before the implementation commit passes."""
    repo = _repo(tmp_path)
    _write(repo, str(ARTIFACT_REL / "PR-7.yaml"), _artifact())
    _commit(repo, "approve plan and tests", date=BASE_TIME)
    _write(repo, "src/backend/safety_boundary/citation_validator.py", "VALUE = 1\n")
    _commit(repo, "implement the validator", date=IMPLEMENTATION_TIME)

    result = _run_gate(repo, "--pr", "7", "--base", "main")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "passed" in result.stdout
    assert "1 implementation commit(s)" in result.stdout


def test_declared_approval_time_decides_not_commit_order(tmp_path: Path) -> None:
    """VS-18: the gate compares `approved_at` to the first implementation commit date."""
    repo = _repo(tmp_path)
    _write(repo, "src/backend/ai_companion/tutor.py", "VALUE = 1\n")
    _commit(repo, "implement the tutor", date=IMPLEMENTATION_TIME)
    # The artifact is committed after the implementation commit, but it declares an
    # approval time that precedes it: the declared time is the contract, so this passes.
    _write(repo, str(ARTIFACT_REL / "PR-7.yaml"), _artifact(approved_at=APPROVAL_TIME))
    _commit(repo, "add the approval artifact", date=LATE_APPROVAL_TIME)

    result = _run_gate(repo, "--pr", "7", "--base", "main")

    assert result.returncode == 0, result.stdout + result.stderr


def test_missing_artifact_fails(tmp_path: Path) -> None:
    """VS-18: a PR with implementation commits and no artifact is blocked."""
    repo = _repo(tmp_path)
    _write(repo, "src/backend/ai_companion/tutor.py", "VALUE = 1\n")
    _commit(repo, "implement without approval", date=IMPLEMENTATION_TIME)

    result = _run_gate(repo, "--pr", "7", "--base", "main")

    _assert_failure(result, "APPROVAL_MISSING")


def test_self_approval_fails(tmp_path: Path) -> None:
    """VS-18 / §7: the approving human is never the author of an implementation commit."""
    repo = _repo(tmp_path)
    _write(repo, str(ARTIFACT_REL / "PR-7.yaml"), _artifact(approver=AUTHOR[0]))
    _commit(repo, "approve own work", date=BASE_TIME)
    _write(repo, "src/backend/ai_companion/tutor.py", "VALUE = 1\n")
    _commit(repo, "implement the tutor", date=IMPLEMENTATION_TIME)

    result = _run_gate(repo, "--pr", "7", "--base", "main")

    _assert_failure(result, "SELF_APPROVAL")


def test_self_approval_detected_by_email(tmp_path: Path) -> None:
    """VS-18: identity matching covers the commit email, not only the display name."""
    repo = _repo(tmp_path)
    _write(repo, str(ARTIFACT_REL / "PR-7.yaml"), _artifact(approver="luming@example.com"))
    _commit(repo, "approve own work", date=BASE_TIME)
    _write(repo, "src/backend/ai_companion/tutor.py", "VALUE = 1\n")
    _commit(repo, "implement the tutor", date=IMPLEMENTATION_TIME)

    result = _run_gate(repo, "--pr", "7", "--base", "main")

    _assert_failure(result, "SELF_APPROVAL")


def test_approval_after_implementation_fails(tmp_path: Path) -> None:
    """VS-18: an approval that postdates the first implementation commit is blocked."""
    repo = _repo(tmp_path)
    _write(repo, "src/backend/ai_companion/tutor.py", "VALUE = 1\n")
    _commit(repo, "implement first", date=IMPLEMENTATION_TIME)
    _write(repo, str(ARTIFACT_REL / "PR-7.yaml"), _artifact(approved_at=LATE_APPROVAL_TIME))
    _commit(repo, "approve retroactively", date=LATE_APPROVAL_TIME)

    result = _run_gate(repo, "--pr", "7", "--base", "main")

    _assert_failure(result, "APPROVAL_AFTER_IMPLEMENTATION")


def test_unknown_requirement_fails(tmp_path: Path) -> None:
    """VS-18: every approved requirement id must resolve in the registry."""
    repo = _repo(tmp_path)
    _write(
        repo,
        str(ARTIFACT_REL / "PR-7.yaml"),
        _artifact(requirement_ids=["NFR-GOV-001", "NFR-GOV-999"]),
    )
    _commit(repo, "approve plan and tests", date=BASE_TIME)
    _write(repo, "src/backend/ai_companion/tutor.py", "VALUE = 1\n")
    _commit(repo, "implement the tutor", date=IMPLEMENTATION_TIME)

    result = _run_gate(repo, "--pr", "7", "--base", "main")

    _assert_failure(result, "REQUIREMENT_UNKNOWN")


@pytest.mark.parametrize(
    ("artifact_kwargs", "reason"),
    [
        ({"rollback": None}, "rollback is required"),
        ({"tests": []}, "tests must be non-empty"),
        ({"requirement_ids": []}, "requirement_ids must be non-empty"),
        ({"approver": ""}, "approver must be non-empty"),
        ({"approved_at": "15/11/2026 10:00"}, "approved_at must be ISO 8601"),
        ({"requirement_ids": ["REQ-LANG-001"]}, "legacy ids are not FR/NFR/INV"),
        ({"pr": 8}, "artifact names a different PR"),
    ],
    ids=[
        "missing-rollback",
        "empty-tests",
        "empty-requirement-ids",
        "empty-approver",
        "non-iso-approved-at",
        "legacy-requirement-id",
        "pr-mismatch",
    ],
)
def test_malformed_artifact_fails(
    tmp_path: Path, artifact_kwargs: dict[str, object], reason: str
) -> None:
    """VS-18: an artifact that cannot be enforced is rejected rather than skipped."""
    repo = _repo(tmp_path)
    _write(repo, str(ARTIFACT_REL / "PR-7.yaml"), _artifact(**artifact_kwargs))
    _commit(repo, "add malformed approval", date=BASE_TIME)
    _write(repo, "src/backend/ai_companion/tutor.py", "VALUE = 1\n")
    _commit(repo, "implement the tutor", date=IMPLEMENTATION_TIME)

    result = _run_gate(repo, "--pr", "7", "--base", "main")

    _assert_failure(result, "APPROVAL_MALFORMED")
    assert reason  # documented in the test id


def test_missing_base_ref_fails_closed(tmp_path: Path) -> None:
    """VS-18: an unresolvable base ref fails instead of passing an unverifiable gate."""
    repo = _repo(tmp_path)
    _write(repo, str(ARTIFACT_REL / "PR-7.yaml"), _artifact())
    _commit(repo, "approve plan and tests", date=BASE_TIME)

    result = _run_gate(repo, "--pr", "7", "--base", "origin/main")

    _assert_failure(result, "BASE_REF_MISSING")


def test_docs_only_changes_need_no_implementation_ordering(tmp_path: Path) -> None:
    """VS-18: with no implementation commits in range, only the artifact is validated."""
    repo = _repo(tmp_path)
    _write(repo, str(ARTIFACT_REL / "PR-7.yaml"), _artifact(approved_at=LATE_APPROVAL_TIME))
    _commit(repo, "approve plan and tests", date=LATE_APPROVAL_TIME)
    _write(repo, "docs/notes.md", "documentation only\n")
    _commit(repo, "document the plan", date=LATE_APPROVAL_TIME)

    result = _run_gate(repo, "--pr", "7", "--base", "main")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "no implementation commits" in result.stdout
