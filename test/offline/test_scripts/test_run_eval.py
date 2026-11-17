"""Gate 4 tests: `scripts/run_eval.py` against a temporary checkout.

Implements: NFR-GOV-001; `verification-constraints.md` VS-13/VS-14/VS-15 and §6;
`docs/code-governance/ci-gates-design.md` §B.5.

Every test builds a throwaway checkout with its own suite file, its own fixture tests
and a copy of the real requirements registry, so a case can be made to pass, fail,
skip, drift or stay pending without touching the repository's suite.

The last test runs the repository's own EVAL-1.0.0 offline tier: it is the integration
check that the shipped suite agrees with `requirements.yaml` and that the two active
cases still pass.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "run_eval.py"
REQUIREMENTS = REPO_ROOT / "docs" / "req" / "requirements.yaml"
REAL_SUITE = "evals/EVAL-1.0.0.yaml"

FIXTURE_TESTS = {
    "tests/test_ok.py": (
        '"""Fixture: a passing case."""\n\n\n'
        "def test_ok() -> None:\n"
        '    """NFR-COST-001 fixture: the assertion that carries the measurement."""\n'
        "    assert 1500 <= 1500\n"
    ),
    "tests/test_fail.py": (
        '"""Fixture: a failing case."""\n\n\n'
        "def test_fail() -> None:\n"
        '    """NFR-QUAL-003 fixture: fails, so an active case must block."""\n'
        "    assert 1 == 2\n"
    ),
    "tests/test_skip.py": (
        '"""Fixture: a skipped case."""\n\n'
        "import pytest\n\n\n"
        '@pytest.mark.skip(reason="fixture: a skipped safety measurement")\n'
        "def test_skipped() -> None:\n"
        '    """NFR-SEC-001 fixture: a skip must be reported as a failure."""\n'
        "    assert False\n"
    ),
    "tests/test_live_sentinel.py": (
        '"""Fixture: proves the offline tier never executes a live case."""\n\n'
        "from pathlib import Path\n\n\n"
        "def test_live_case_ran() -> None:\n"
        '    """NFR-PERF-001 fixture: leaves a sentinel only if it is executed."""\n'
        '    Path("live-case-ran.txt").write_text("executed\\n", encoding="utf-8")\n'
        "    assert False\n"
    ),
}


def _case(**overrides: object) -> dict[str, object]:
    case: dict[str, object] = {
        "id": "fixture-case",
        "tier": "offline",
        "requirement": "NFR-COST-001",
        "threshold": 1500,
        "comparator": "lte",
        "test": "tests/test_ok.py::test_ok",
        "status": "active",
    }
    case.update(overrides)
    return case


def _checkout(tmp_path: Path, cases: list[dict[str, object]]) -> Path:
    """Create a throwaway checkout containing one suite file and the fixture tests."""
    root = tmp_path / "root"
    (root / "docs" / "req").mkdir(parents=True)
    (root / "docs" / "req" / "requirements.yaml").write_text(
        REQUIREMENTS.read_text(encoding="utf-8"), encoding="utf-8"
    )
    for relative, source in FIXTURE_TESTS.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
    (root / "evals").mkdir()
    (root / "evals" / "EVAL-TEST.yaml").write_text(
        yaml.safe_dump({"suite": "EVAL-TEST", "version": "0.0.1", "cases": cases}, sort_keys=False),
        encoding="utf-8",
    )
    return root


def _run(
    root: Path,
    *args: str,
    env: dict[str, str] | None = None,
    suite: str = "evals/EVAL-TEST.yaml",
) -> subprocess.CompletedProcess[str]:
    """Run the gate with a clean live-credential environment unless a test sets them."""
    run_env = os.environ.copy()
    run_env.pop("LLM_MODE", None)
    run_env.pop("LLM_API_KEY", None)
    if env:
        run_env.update(env)
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--suite", suite, "--root", str(root), *args],
        cwd=str(root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=run_env,
        check=False,
    )


def _assert_failure(result: subprocess.CompletedProcess[str], code: str) -> None:
    assert result.returncode == 1, result.stdout + result.stderr
    assert code in result.stderr, result.stdout + result.stderr


def test_offline_active_case_passing_exits_zero(tmp_path: Path) -> None:
    """VS-12 / §B.3: a passing active offline case passes the gate."""
    root = _checkout(tmp_path, [_case()])

    result = _run(root, "--offline")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "fixture-case PASS" in result.stdout


def test_offline_active_case_failing_exits_one(tmp_path: Path) -> None:
    """§B.3: an active case whose test fails blocks the pull request."""
    root = _checkout(tmp_path, [_case(requirement="NFR-QUAL-003", threshold=1.0, comparator="eq", test="tests/test_fail.py::test_fail")])

    result = _run(root, "--offline")

    assert result.returncode == 1, result.stdout + result.stderr
    assert "fixture-case FAIL" in result.stdout


def test_skipped_case_is_a_failure(tmp_path: Path) -> None:
    """§6: a skipped safety measurement is reported as a failure, never as a pass."""
    root = _checkout(
        tmp_path,
        [_case(requirement="NFR-SEC-001", threshold=0, comparator="zero", test="tests/test_skip.py::test_skipped")],
    )

    result = _run(root, "--offline")

    assert result.returncode == 1, result.stdout + result.stderr
    assert "skipped" in result.stdout


def test_pending_case_is_reported_without_gating(tmp_path: Path) -> None:
    """§B.1: a `pending` metric is reported and never blocks a pull request."""
    root = _checkout(
        tmp_path,
        [_case(requirement="NFR-QUAL-003", threshold=1.0, comparator="eq", test="tests/test_fail.py::test_fail", status="pending")],
    )

    result = _run(root, "--offline")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "SKIPPED_PENDING" in result.stdout
    assert "FAIL" not in result.stdout


def test_missing_test_node_fails(tmp_path: Path) -> None:
    """§B.3: an active case with no test node has no measurement, so it fails."""
    root = _checkout(tmp_path, [_case(test="tests/test_absent.py::test_nothing")])

    result = _run(root, "--offline")

    assert result.returncode == 1, result.stdout + result.stderr
    assert "does not exist" in result.stdout


def test_threshold_drift_fails(tmp_path: Path) -> None:
    """§B.2: the suite threshold must equal the registry threshold, unit included."""
    root = _checkout(tmp_path, [_case(requirement="NFR-PERF-001", threshold=13.0, comparator="lte")])

    result = _run(root, "--offline")

    _assert_failure(result, "THRESHOLD_DRIFT")


def test_unknown_requirement_fails(tmp_path: Path) -> None:
    """§B.2: every suite case cites a requirement that exists in the registry."""
    root = _checkout(tmp_path, [_case(requirement="NFR-GOV-999")])

    result = _run(root, "--offline")

    _assert_failure(result, "REQUIREMENT_UNKNOWN")


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"comparator": "gt"}, "unknown comparator"),
        ({"status": "blocking"}, "unknown status"),
        ({"tier": "staging"}, "unknown tier"),
        ({"threshold": "1500"}, "threshold must be numeric"),
        ({"test": "tests/test_ok.py"}, "test must be a node id"),
    ],
    ids=["comparator", "status", "tier", "threshold-type", "node-id"],
)
def test_malformed_suite_is_rejected(
    tmp_path: Path, overrides: dict[str, object], reason: str
) -> None:
    """§B.3: the suite is schema-validated before anything runs."""
    root = _checkout(tmp_path, [_case(**overrides)])

    result = _run(root, "--offline")

    _assert_failure(result, "SUITE_INVALID")
    assert reason  # documented in the test id


def test_offline_never_runs_live_cases(tmp_path: Path) -> None:
    """§B.1: the offline tier runs offline cases only; a live case is not executed."""
    root = _checkout(
        tmp_path,
        [
            _case(),
            _case(
                id="live-case",
                tier="live",
                requirement="NFR-PERF-001",
                threshold=12.0,
                test="tests/test_live_sentinel.py::test_live_case_ran",
            ),
        ],
    )

    result = _run(root, "--offline")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "live-case" not in result.stdout
    assert not (root / "live-case-ran.txt").exists()


def test_live_fails_closed_without_credentials(tmp_path: Path) -> None:
    """§B.1 / §3: a release-bound live run without credentials fails, it does not skip."""
    root = _checkout(
        tmp_path,
        [
            _case(
                id="live-case",
                tier="live",
                requirement="NFR-PERF-001",
                threshold=12.0,
                test="tests/test_ok.py::test_ok",
            )
        ],
    )

    result = _run(root, "--live")

    _assert_failure(result, "LIVE_ENV_MISSING")


def test_live_allow_skip_reports_skip_and_passes(tmp_path: Path) -> None:
    """§B.3: `--allow-skip` is the pull-request context; it records the exception."""
    root = _checkout(
        tmp_path,
        [
            _case(
                id="live-case",
                tier="live",
                requirement="NFR-PERF-001",
                threshold=12.0,
                test="tests/test_ok.py::test_ok",
            )
        ],
    )

    result = _run(root, "--live", "--allow-skip")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "SKIP_LIVE_NO_ENV" in result.stdout


def test_live_with_env_but_no_active_case_fails_closed(tmp_path: Path) -> None:
    """§3: a live run that measures nothing is not a passing Tier 3."""
    root = _checkout(
        tmp_path,
        [
            _case(
                id="live-case",
                tier="live",
                requirement="NFR-PERF-001",
                threshold=12.0,
                test="tests/test_ok.py::test_ok",
                status="pending",
            )
        ],
    )

    result = _run(root, "--live", env={"LLM_MODE": "live", "LLM_API_KEY": "capped-key"})

    _assert_failure(result, "LIVE_NO_ACTIVE_CASES")


def test_evidence_is_written_with_counts(tmp_path: Path) -> None:
    """§9: evidence is reported with n, suite version, tier and date."""
    root = _checkout(tmp_path, [_case()])

    result = _run(root, "--offline")

    assert result.returncode == 0, result.stdout + result.stderr
    evidence_files = sorted((root / "reports" / "eval").glob("offline-EVAL-TEST-*.json"))
    assert len(evidence_files) == 1, evidence_files
    evidence = json.loads(evidence_files[0].read_text(encoding="utf-8"))
    assert evidence["suite"] == "EVAL-TEST"
    assert evidence["version"] == "0.0.1"
    assert evidence["tier"] == "offline"
    assert evidence["generated_at"]
    assert evidence["totals"]["cases_in_tier"] == 1
    assert evidence["totals"]["passed"] == 1
    assert evidence["result"] == "PASS"


def test_repository_suite_passes_offline(tmp_path: Path) -> None:
    """VS-13: the shipped EVAL-1.0.0 suite agrees with the registry and its active cases pass."""
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--suite",
            REAL_SUITE,
            "--root",
            str(REPO_ROOT),
            "--report-dir",
            str(tmp_path / "evidence"),
            "--offline",
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "citation-validity PASS" in result.stdout
    assert "prompt-tokens PASS" in result.stdout
    assert "3 pending" in result.stdout
