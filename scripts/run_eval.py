"""Gate 4 - semantic evaluation: offline on every PR, live at release.

Implements: ADR-010 G3; `verification-constraints.md` §3-§4 and VS-13/VS-14/VS-15;
`docs/code-governance/ci-gates-design.md` Part B.

Canonical commands:
    python scripts/run_eval.py --suite evals/EVAL-1.0.0.yaml --offline
    python scripts/run_eval.py --suite evals/EVAL-1.0.0.yaml --live

What the runner does, in order:

1. Load `evals/<suite>.yaml` and validate every case against the suite schema
   (`SUITE_INVALID`).
2. Check every threshold against `docs/req/requirements.yaml`, which stays the
   single source of truth (`THRESHOLD_DRIFT`, `REQUIREMENT_UNKNOWN`).
3. `--offline`: run the `tier: offline` + `status: active` cases with pytest.
   A `pending` case is reported as `SKIPPED_PENDING` and never blocks a pull
   request. Any active failure, a missing test node, or a skipped test fails the
   gate: a skipped safety test is a failed safety test (§6).
4. `--live`: require `LLM_MODE=live` and a capped `LLM_API_KEY`. Without them the
   gate fails closed (`LIVE_ENV_MISSING`), unless `--allow-skip` is passed in a
   pull-request context, which reports `SKIP_LIVE_NO_ENV` and exits 0. A live run
   with no active live case fails closed (`LIVE_NO_ACTIVE_CASES`), because a
   missing Tier-3 measurement is not a passing Tier-3 measurement (§3).
5. Write evidence to `reports/eval/` as JSON: n, suite version, tier, date and every
   per-case outcome, per §9 ("every metric is reported with n, the eval version,
   the corpus/prompt/model version and the date").

Exit 0 on pass or an allowed skip; exit 1 on any failure, always with one typed code
on stderr.

The offline tier reports the assertion outcome, not a hand-copied number: the node
id carries the measurement because the test itself asserts the threshold in the
suite. The live tier is where the numeric score is produced.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

DEFAULT_SUITE = Path("evals") / "EVAL-1.0.0.yaml"
DEFAULT_REQUIREMENTS = Path("docs") / "req" / "requirements.yaml"
DEFAULT_REPORT_DIR = Path("reports") / "eval"

TIERS = frozenset({"offline", "live"})
COMPARATORS = frozenset({"eq", "gte", "lte", "zero"})
STATUSES = frozenset({"active", "pending"})

CASE_FIELDS = frozenset(
    {"id", "tier", "requirement", "threshold", "comparator", "test", "status"}
)

#: Per-case pytest budget. A hung provider call is a failed case, not a hung gate.
CASE_TIMEOUT_SECONDS = 900

#: Environment contract for the live tier (capped key, release-approved).
LIVE_MODE_VAR = "LLM_MODE"
LIVE_KEY_VAR = "LLM_API_KEY"

#: Threshold phrases understood in a fit criterion, in the registry's own words.
_COMPARATOR = re.compile(r"(>=|<=|\u2265|\u2264|==|=)\s*(\d+(?:\.\d+)?)")
_PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s*%")
_ZERO_COUNT = re.compile(r"\b0\s+[A-Za-z]")
_THOUSANDS_SEPARATOR = re.compile(r"(?<=\d),(?=\d{3}(?!\d))")

_COMPARATOR_NAMES = {
    ">=": "gte",
    "\u2265": "gte",
    "<=": "lte",
    "\u2264": "lte",
    "==": "eq",
    "=": "eq",
}

PASS = "PASS"
FAIL = "FAIL"
SKIPPED_PENDING = "SKIPPED_PENDING"
SKIP_LIVE_NO_ENV = "SKIP_LIVE_NO_ENV"


class GateFailure(Exception):
    """A gate outcome carrying the typed code CI reports."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class Case:
    """One evaluation case from the suite."""

    id: str
    tier: str
    requirement: str
    threshold: float
    comparator: str
    test: str
    status: str


@dataclass
class CaseResult:
    """One case outcome, as reported in the console and the evidence file."""

    case: Case
    outcome: str
    detail: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.case.id,
            "tier": self.case.tier,
            "requirement": self.case.requirement,
            "threshold": self.case.threshold,
            "comparator": self.case.comparator,
            "status": self.case.status,
            "test": self.case.test,
            "outcome": self.outcome,
            "detail": self.detail,
        }


@dataclass
class RunSummary:
    """The whole run, written to `reports/eval/` as evidence."""

    suite: str
    version: str
    tier: str
    results: list[CaseResult] = field(default_factory=list)

    def count(self, outcome: str) -> int:
        return sum(1 for result in self.results if result.outcome == outcome)

    @property
    def failed(self) -> bool:
        return any(result.outcome == FAIL for result in self.results)

    def as_evidence(self) -> dict[str, Any]:
        active = sum(1 for result in self.results if result.case.status == "active")
        return {
            "suite": self.suite,
            "version": self.version,
            "tier": self.tier,
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "totals": {
                "cases_in_tier": len(self.results),
                "active": active,
                "passed": self.count(PASS),
                "failed": self.count(FAIL),
                "pending": self.count(SKIPPED_PENDING),
                "skipped_live_no_env": self.count(SKIP_LIVE_NO_ENV),
            },
            "result": FAIL if self.failed else PASS,
            "cases": [result.as_dict() for result in self.results],
        }


def repo_root() -> Path:
    """Return the repository root, falling back to the script's parent directory."""
    fallback = Path(__file__).resolve().parent.parent
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(fallback),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError:
        return fallback
    if result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip())
    return fallback


def load_yaml(path: Path, *, code: str, what: str) -> Any:
    """Read YAML, mapping every read/parse failure to one typed code."""
    if not path.is_file():
        raise GateFailure(code, f"{what} not found at {path.as_posix()}")
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise GateFailure(code, f"{what} at {path.as_posix()} cannot be parsed: {exc}") from exc


def load_suite(path: Path) -> tuple[str, str, list[Case]]:
    """Load and validate the suite; raise `SUITE_INVALID` on any schema gap."""
    document = load_yaml(path, code="SUITE_INVALID", what="suite")
    if not isinstance(document, Mapping):
        raise GateFailure("SUITE_INVALID", f"{path.as_posix()} must be a YAML mapping")

    suite = document.get("suite")
    version = document.get("version")
    if not isinstance(suite, str) or not suite.strip():
        raise GateFailure("SUITE_INVALID", f"{path.as_posix()}: suite must be a non-empty string")
    if not isinstance(version, str) or not version.strip():
        raise GateFailure("SUITE_INVALID", f"{path.as_posix()}: version must be a non-empty string")

    raw_cases = document.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise GateFailure("SUITE_INVALID", f"{path.as_posix()}: cases must be a non-empty list")

    cases = [_validate_case(entry, path, index) for index, entry in enumerate(raw_cases)]
    ids = [case.id for case in cases]
    duplicates = sorted({case_id for case_id in ids if ids.count(case_id) > 1})
    if duplicates:
        raise GateFailure("SUITE_INVALID", f"{path.as_posix()}: duplicate case ids {duplicates}")
    return suite.strip(), version.strip(), cases


def _validate_case(entry: Any, path: Path, index: int) -> Case:
    if not isinstance(entry, Mapping):
        raise GateFailure("SUITE_INVALID", f"{path.as_posix()}: cases[{index}] must be a mapping")
    extra = set(entry) - CASE_FIELDS
    missing = CASE_FIELDS - set(entry)
    if missing:
        raise GateFailure(
            "SUITE_INVALID", f"{path.as_posix()}: cases[{index}] is missing {sorted(missing)}"
        )
    if extra:
        raise GateFailure(
            "SUITE_INVALID", f"{path.as_posix()}: cases[{index}] has unknown fields {sorted(extra)}"
        )

    case_id = entry["id"]
    if not isinstance(case_id, str) or not case_id.strip():
        raise GateFailure("SUITE_INVALID", f"{path.as_posix()}: cases[{index}].id must be a string")
    tier = entry["tier"]
    if tier not in TIERS:
        raise GateFailure(
            "SUITE_INVALID",
            f"{path.as_posix()}: {case_id}: tier must be one of {sorted(TIERS)}, found {tier!r}",
        )
    requirement = entry["requirement"]
    if not isinstance(requirement, str) or not requirement.strip():
        raise GateFailure(
            "SUITE_INVALID", f"{path.as_posix()}: {case_id}: requirement must be a string"
        )
    threshold = entry["threshold"]
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
        raise GateFailure(
            "SUITE_INVALID", f"{path.as_posix()}: {case_id}: threshold must be a number"
        )
    comparator = entry["comparator"]
    if comparator not in COMPARATORS:
        raise GateFailure(
            "SUITE_INVALID",
            f"{path.as_posix()}: {case_id}: comparator must be one of "
            f"{sorted(COMPARATORS)}, found {comparator!r}",
        )
    test = entry["test"]
    if not isinstance(test, str) or "::" not in test:
        raise GateFailure(
            "SUITE_INVALID",
            f"{path.as_posix()}: {case_id}: test must be a pytest node id 'path::test'",
        )
    status = entry["status"]
    if status not in STATUSES:
        raise GateFailure(
            "SUITE_INVALID",
            f"{path.as_posix()}: {case_id}: status must be one of {sorted(STATUSES)}, "
            f"found {status!r}",
        )

    return Case(
        id=case_id.strip(),
        tier=str(tier),
        requirement=requirement.strip(),
        threshold=float(threshold),
        comparator=str(comparator),
        test=test.strip(),
        status=str(status),
    )


def load_requirements(path: Path) -> dict[str, Mapping[str, Any]]:
    """Return requirement entries keyed by id."""
    document = load_yaml(path, code="REQUIREMENTS_MISSING", what="requirements registry")
    if not isinstance(document, Mapping):
        raise GateFailure("REQUIREMENTS_MISSING", f"{path.as_posix()} must be a YAML mapping")
    entries = document.get("requirements")
    if not isinstance(entries, list):
        raise GateFailure("REQUIREMENTS_MISSING", f"{path.as_posix()} has no requirements list")
    registry: dict[str, Mapping[str, Any]] = {}
    for entry in entries:
        if isinstance(entry, Mapping) and isinstance(entry.get("id"), str):
            registry[str(entry["id"]).strip()] = entry
    if not registry:
        raise GateFailure("REQUIREMENTS_MISSING", f"{path.as_posix()} declares no requirement ids")
    return registry


def extract_thresholds(text: str) -> list[tuple[str, float]]:
    """Read the threshold phrases a fit criterion states, e.g. '>= 0.85' or '1,500'.

    Returns ``(comparator, value)`` pairs; percentages are normalised to fractions
    ('100%' -> ('eq', 1.0)) and a bare zero count becomes ('zero', 0.0).
    """
    cleaned = _THOUSANDS_SEPARATOR.sub("", text)
    pairs: list[tuple[str, float]] = [
        (_COMPARATOR_NAMES[operator], float(number))
        for operator, number in _COMPARATOR.findall(cleaned)
    ]
    pairs.extend(("eq", float(number) / 100.0) for number in _PERCENT.findall(cleaned))
    if _ZERO_COUNT.search(cleaned):
        pairs.append(("zero", 0.0))
    return pairs


def threshold_matches(case: Case, requirement: dict[str, Any]) -> bool:
    """True when the registry states the case's threshold and comparator."""
    text = f"{requirement.get('statement', '')} {requirement.get('fit_criterion', '')}"
    for comparator, value in extract_thresholds(text):
        if comparator != case.comparator:
            continue
        if round(value, 9) == round(case.threshold, 9):
            return True
    return False


def check_thresholds(cases: Sequence[Case], registry: dict[str, Mapping[str, Any]]) -> None:
    """Fail on drift between the suite and the registry; the registry stays authoritative."""
    for case in cases:
        requirement = registry.get(case.requirement)
        if requirement is None:
            raise GateFailure(
                "REQUIREMENT_UNKNOWN",
                f"{case.id}: {case.requirement} is not declared in the requirements registry",
            )
        if not threshold_matches(case, dict(requirement)):
            stated = extract_thresholds(
                f"{requirement.get('statement', '')} {requirement.get('fit_criterion', '')}"
            )
            raise GateFailure(
                "THRESHOLD_DRIFT",
                f"{case.id}: suite says {case.comparator} {case.threshold:g} but "
                f"{case.requirement} states {stated or 'no threshold'}",
            )


def _pytest_junit_counts(junit_path: Path) -> tuple[int, int, int] | None:
    """Return (tests, failed, skipped) from a JUnit XML report, or None if unreadable."""
    if not junit_path.is_file():
        return None
    try:
        tree = ElementTree.parse(junit_path)
    except (ElementTree.ParseError, OSError):
        return None
    root = tree.getroot()
    suites = [root] if root.tag == "testsuite" else list(root)
    tests = failed = skipped = 0
    for suite in suites:
        if suite.tag != "testsuite":
            continue
        tests += int(suite.get("tests", 0) or 0)
        failed += int(suite.get("failures", 0) or 0) + int(suite.get("errors", 0) or 0)
        skipped += int(suite.get("skipped", 0) or 0)
    return tests, failed, skipped


def run_case(root: Path, case: Case) -> CaseResult:
    """Run one case's pytest node and map the result to an outcome."""
    test_file = case.test.split("::", 1)[0]
    if not (root / test_file).is_file():
        return CaseResult(
            case=case,
            outcome=FAIL,
            detail=f"test file {test_file} does not exist; the case is active but unmeasured",
        )

    with tempfile.TemporaryDirectory(prefix="eval-") as scratch:
        junit_path = Path(scratch) / "report.xml"
        try:
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    case.test,
                    "-q",
                    "-p",
                    "no:cacheprovider",
                    f"--junitxml={junit_path}",
                ],
                cwd=str(root),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=CASE_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return CaseResult(
                case=case,
                outcome=FAIL,
                detail=f"pytest exceeded {CASE_TIMEOUT_SECONDS}s",
            )

        counts = _pytest_junit_counts(junit_path)
        if counts is None:
            tail = (completed.stdout + completed.stderr).strip().splitlines()[-3:]
            return CaseResult(
                case=case,
                outcome=FAIL,
                detail="no test report produced (" + " / ".join(tail) + ")",
            )
        tests, failed, skipped = counts

    if tests == 0:
        return CaseResult(case=case, outcome=FAIL, detail="no tests collected for the node id")
    if skipped:
        return CaseResult(
            case=case,
            outcome=FAIL,
            detail=f"{skipped} skipped (a skipped measurement is not a pass)",
        )
    if failed or completed.returncode != 0:
        return CaseResult(
            case=case,
            outcome=FAIL,
            detail=f"{failed} failed / {tests} collected (pytest exit {completed.returncode})",
        )
    return CaseResult(case=case, outcome=PASS, detail=f"{tests} passed")


def live_credentials_present() -> bool:
    """The live tier needs an explicit live mode and a capped key."""
    return os.environ.get(LIVE_MODE_VAR, "").strip().lower() == "live" and bool(
        os.environ.get(LIVE_KEY_VAR, "").strip()
    )


def run_tier(
    tier: str,
    cases: Sequence[Case],
    root: Path,
    *,
    allow_skip: bool,
) -> RunSummary:
    """Run one tier and return its summary."""
    summary = RunSummary(suite="", version="", tier=tier)
    tier_cases = [case for case in cases if case.tier == tier]

    if tier == "live" and not live_credentials_present():
        if allow_skip:
            summary.results.extend(
                CaseResult(
                    case=case,
                    outcome=SKIP_LIVE_NO_ENV,
                    detail=f"{LIVE_MODE_VAR}=live and {LIVE_KEY_VAR} are absent; skipped in PR context",
                )
                for case in tier_cases
            )
            return summary
        raise GateFailure(
            "LIVE_ENV_MISSING",
            f"the live tier needs {LIVE_MODE_VAR}=live and {LIVE_KEY_VAR}; "
            "a release-bound run fails closed rather than skipping",
        )

    if tier == "live" and not any(case.status == "active" for case in tier_cases):
        raise GateFailure(
            "LIVE_NO_ACTIVE_CASES",
            "no active live case; a release-bound Tier 3 run without a measurement fails closed",
        )

    for case in tier_cases:
        if case.status == "pending":
            summary.results.append(
                CaseResult(
                    case=case,
                    outcome=SKIPPED_PENDING,
                    detail="metric declared but unmeasured; reported, does not gate a PR",
                )
            )
            continue
        summary.results.append(run_case(root, case))
    return summary


def write_evidence(report_dir: Path, summary: RunSummary) -> Path:
    """Write the run's evidence JSON and return its path."""
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = report_dir / f"{summary.tier}-{summary.suite}-{stamp}.json"
    path.write_text(
        json.dumps(summary.as_evidence(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def _report(summary: RunSummary, evidence: Path) -> None:
    for result in summary.results:
        case = result.case
        print(
            f"run_eval: {case.id} {result.outcome} "
            f"({case.requirement} {case.comparator} {case.threshold:g}; "
            f"{case.tier}/{case.status}) - {result.detail}"
        )
    pending = summary.count(SKIPPED_PENDING)
    skipped = summary.count(SKIP_LIVE_NO_ENV)
    verdict = FAIL if summary.failed else PASS
    print(
        f"run_eval: {summary.tier} tier {verdict}; "
        f"{summary.count(PASS)} passed, {summary.count(FAIL)} failed, "
        f"{pending} pending (reported, not gating), {skipped} skipped for missing live env; "
        f"evidence: {evidence.as_posix()}."
    )


def _fail(code: str, message: str) -> int:
    print(f"run_eval: {code}: {message}", file=sys.stderr)
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print(f"::error title=Gate 4 ({code})::{message}")
    return 1


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Gate 4: run the fixed semantic evaluation suite.",
    )
    parser.add_argument("--suite", required=True, help="suite path, e.g. evals/EVAL-1.0.0.yaml")
    tier = parser.add_mutually_exclusive_group(required=True)
    tier.add_argument("--offline", action="store_true", help="run the offline tier (per PR)")
    tier.add_argument("--live", action="store_true", help="run the live tier (release)")
    parser.add_argument(
        "--allow-skip",
        action="store_true",
        help="live tier only: report SKIP_LIVE_NO_ENV instead of failing when credentials are absent",
    )
    parser.add_argument(
        "--root",
        default=None,
        help="checkout root to evaluate (default: the repository containing this script)",
    )
    parser.add_argument(
        "--requirements",
        default=None,
        help=f"requirements registry (default: {DEFAULT_REQUIREMENTS.as_posix()})",
    )
    parser.add_argument(
        "--report-dir",
        default=None,
        help=f"evidence directory (default: {DEFAULT_REPORT_DIR.as_posix()})",
    )
    return parser.parse_args(list(argv))


def _resolve(root: Path, value: str | None, default: Path) -> Path:
    if value is None:
        return root / default
    candidate = Path(value)
    return candidate if candidate.is_absolute() else root / candidate


def main(argv: Sequence[str]) -> int:
    args = _parse_args(argv)
    tier = "offline" if args.offline else "live"
    try:
        root = Path(args.root).resolve() if args.root else repo_root()
        suite_path = _resolve(root, args.suite, DEFAULT_SUITE)
        requirements_path = _resolve(root, args.requirements, DEFAULT_REQUIREMENTS)
        report_dir = _resolve(root, args.report_dir, DEFAULT_REPORT_DIR)

        suite, version, cases = load_suite(suite_path)
        registry = load_requirements(requirements_path)
        check_thresholds(cases, registry)

        summary = run_tier(tier, cases, root, allow_skip=args.allow_skip and tier == "live")
        summary.suite = suite
        summary.version = version
        evidence = write_evidence(report_dir, summary)
    except GateFailure as failure:
        return _fail(failure.code, failure.message)

    _report(summary, evidence)
    return 1 if summary.failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
