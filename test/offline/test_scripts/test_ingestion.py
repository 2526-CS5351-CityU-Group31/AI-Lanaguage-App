"""Offline tests for the FR-CORP-001 content ingestion command.

Every test names FR-CORP-001 (or INV-SEC-001/INV-CITE-001) in its docstring so
the traceability check can resolve it. No test touches the network or a real
database: the connection is a deterministic fake that records every statement.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "ingest_content.py"

# 80 distinct sentences (~1,300 estimated tokens) force several chunks and at
# least one overlap boundary under the 400-token ceiling.
LONG_TEXT = " ".join(
    f"Point {index} explains that the present simple describes habits and routines."
    for index in range(80)
)


@pytest.fixture(scope="module")
def ingest():
    """Load scripts/ingest_content.py as a module without importing a package."""
    spec = importlib.util.spec_from_file_location(
        "ingest_content_under_test", SCRIPT_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeCursor:
    """Minimal psycopg cursor result used by the fake connection."""

    def __init__(self, *, rows: list[tuple[Any, ...]] | None = None,
                 one: tuple[Any, ...] | None = None) -> None:
        self._rows = rows or []
        self._one = one

    def fetchone(self) -> tuple[Any, ...] | None:
        """Return the single row or ``None``."""
        return self._one

    def fetchall(self) -> list[tuple[Any, ...]]:
        """Return all rows."""
        return self._rows


class FakeConnection:
    """Record every statement and simulate the few reads ingestion needs."""

    def __init__(
        self,
        *,
        role: str = "ingest_admin",
        existing_chunks: int = 0,
        fail_on: str | None = None,
    ) -> None:
        self.role = role
        self.existing_chunks = existing_chunks
        self.fail_on = fail_on
        self.calls: list[tuple[str, tuple[Any, ...] | None]] = []
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> FakeCursor:
        """Record and answer one SQL statement."""
        text = " ".join(sql.split())
        self.calls.append((text, params))
        if self.fail_on and self.fail_on in text:
            raise RuntimeError("write failed")
        if text.startswith("SELECT current_user"):
            return FakeCursor(one=(self.role,))
        if text.startswith("DELETE FROM content_chunks"):
            return FakeCursor(
                rows=[(f"stale-{index}",) for index in range(self.existing_chunks)]
            )
        return FakeCursor()

    def commit(self) -> None:
        """Record a commit."""
        self.commits += 1

    def rollback(self) -> None:
        """Record a rollback."""
        self.rollbacks += 1

    def close(self) -> None:
        """Record a close."""
        self.closed = True

    def statements(self, prefix: str) -> list[tuple[str, tuple[Any, ...] | None]]:
        """Return recorded statements starting with ``prefix``."""
        return [call for call in self.calls if call[0].startswith(prefix)]


def make_source(**overrides: Any) -> dict[str, Any]:
    """Return one valid A2 source, with optional field overrides."""
    source: dict[str, Any] = {
        "source_id": "a2-grammar-present-simple",
        "title": "Present Simple",
        "language": "en",
        "level": "A2",
        "topic": "grammar",
        "review_status": "published",
        "sections": [{"section": "Form", "text": LONG_TEXT}],
    }
    source.update(overrides)
    return source


def make_manifest(directory: Path, *sources: dict[str, Any]) -> Path:
    """Write a version-1 manifest and return its path."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "manifest.yaml"
    path.write_text(
        yaml.safe_dump({"version": 1, "sources": list(sources)}, sort_keys=False),
        encoding="utf-8",
    )
    return path


def test_admin_ingest_pipeline(ingest, tmp_path):
    """FR-CORP-001: the admin command indexes published chunks and audits every source."""
    manifest = make_manifest(
        tmp_path,
        make_source(),
        make_source(source_id="a2-grammar-draft", review_status="draft"),
    )
    pipeline = ingest.IngestPipeline(actor="qa-test")
    plan = pipeline.build_plan(manifest)
    connection = FakeConnection()

    report = pipeline.execute(plan, connection=connection, embeddings={})
    payload = report.as_dict()

    assert payload["status"] == "ok"
    assert payload["dry_run"] is False
    assert payload["database_role"] == "ingest_admin"
    assert payload["published_sources"] == 1
    assert payload["skipped_sources"] == 1
    assert payload["chunks"] > 1
    assert payload["planned_chunks"] > payload["chunks"]
    assert {chunk.source_id for chunk in plan.chunks} == {
        "a2-grammar-present-simple"
    }

    assert connection.commits == 1
    assert connection.rollbacks == 0
    assert len(connection.statements("INSERT INTO content_sources")) == 2
    assert (
        len(connection.statements("INSERT INTO content_chunks"))
        == payload["chunks"]
    )
    audit = connection.statements("INSERT INTO content_audit")
    assert {call[1][0] for call in audit if call[1]} == {"ingest", "skip"}
    assert all(
        call[1][6] is None
        for call in connection.statements("INSERT INTO content_chunks")
        if call[1]
    )


def test_dry_run_writes_no_rows(ingest, tmp_path):
    """FR-CORP-001: a dry run emits the chunk plan and performs zero database writes."""
    manifest = make_manifest(tmp_path, make_source())
    pipeline = ingest.IngestPipeline(actor="qa-test")
    plan = pipeline.build_plan(manifest)

    report = pipeline.execute(plan, dry_run=True)
    payload = report.as_dict()

    assert payload["dry_run"] is True
    assert payload["database_role"] is None
    assert payload["chunks"] == len(payload["chunk_plan"])
    assert payload["chunk_plan"][0]["text"].startswith("Point 0")
    assert payload["published_sources"] == 1


def test_dry_run_shows_draft_chunks_for_review(ingest, tmp_path):
    """FR-CORP-001: drafts are chunked for review but never written or citable."""
    manifest = make_manifest(tmp_path, make_source(review_status="draft"))
    pipeline = ingest.IngestPipeline(actor="qa-test")
    plan = pipeline.build_plan(manifest)

    payload = pipeline.execute(plan, dry_run=True).as_dict()

    assert plan.chunks == ()
    assert plan.planned_chunks
    assert payload["published_sources"] == 0
    assert payload["skipped_sources"] == 1
    assert payload["planned_chunks"] == len(payload["chunk_plan"])
    assert payload["chunks"] == 0
    assert all(item["review_status"] == "draft" for item in payload["chunk_plan"])

    connection = FakeConnection()
    real = pipeline.execute(plan, connection=connection, embeddings={})
    assert real.as_dict()["chunks"] == 0
    assert not connection.statements("INSERT INTO content_chunks")
    assert connection.commits == 1


def test_cli_dry_run_needs_no_database(ingest, tmp_path, monkeypatch):
    """FR-CORP-001: the CLI dry run needs no ADMIN_DATABASE_URL and no connection."""
    manifest = make_manifest(tmp_path, make_source())
    report_path = tmp_path / "report.json"
    monkeypatch.delenv("ADMIN_DATABASE_URL", raising=False)
    monkeypatch.setattr(
        ingest,
        "_connect",
        lambda dsn: (_ for _ in ()).throw(AssertionError("must not connect")),
    )

    code = ingest.main(
        [
            "--manifest",
            str(manifest),
            "--dry-run",
            "--report",
            str(report_path),
            "--actor",
            "qa-test",
        ]
    )

    assert code == 0
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["dry_run"] is True
    assert payload["actor"] == "qa-test"
    assert payload["manifest_sha256"]


@pytest.mark.parametrize(
    ("sources", "expected"),
    [
        (
            [make_source(), make_source()],
            "duplicated",
        ),
        (
            [make_source(language="fr")],
            "language",
        ),
        (
            [make_source(level="C1")],
            "level",
        ),
        (
            [make_source(review_status="published", sections=[])],
            "sections",
        ),
        (
            [make_source(sections=[{"section": "Form", "text": "   "}])],
            "non-empty",
        ),
        (
            [dict(make_source(), unexpected=True)],
            "unknown field",
        ),
        (
            [make_source(review_status="live")],
            "review_status",
        ),
    ],
)
def test_manifest_validation_fails_closed(ingest, tmp_path, sources, expected):
    """FR-CORP-001: malformed manifests abort before any database access."""
    manifest = make_manifest(tmp_path, *sources)
    with pytest.raises(ingest.IngestError, match=expected):
        ingest.load_manifest(manifest)


def test_manifest_path_cannot_escape_its_directory(ingest, tmp_path):
    """FR-CORP-001: a section path may not read outside the manifest directory."""
    outside = tmp_path.parent / "outside-secret.md"
    outside.write_text("do not ingest me", encoding="utf-8")
    manifest = make_manifest(
        tmp_path,
        make_source(sections=[{"section": "Form", "path": "../outside-secret.md"}]),
    )

    with pytest.raises(ingest.IngestError, match="escapes"):
        ingest.load_manifest(manifest)


def test_section_path_is_resolved_from_the_manifest(ingest, tmp_path):
    """FR-CORP-001: a section may be loaded from a UTF-8 file next to the manifest."""
    lesson = tmp_path / "lesson.md"
    lesson.write_text(LONG_TEXT, encoding="utf-8")
    manifest = make_manifest(
        tmp_path,
        make_source(sections=[{"section": "Form", "path": "lesson.md"}]),
    )

    plan = ingest.IngestPipeline(actor="qa-test").build_plan(manifest)

    assert plan.chunks
    assert all(chunk.section == "Form" for chunk in plan.chunks)


def test_chunks_stay_within_token_bounds_with_overlap(ingest, tmp_path):
    """FR-CORP-001: chunks are non-empty, never exceed 400 tokens and overlap by <=10%."""
    manifest = make_manifest(tmp_path, make_source())
    plan = ingest.IngestPipeline(actor="qa-test").build_plan(manifest)

    tokens = [chunk.token_count for chunk in plan.chunks]
    texts = [chunk.text for chunk in plan.chunks]

    assert len(tokens) >= 3
    assert all(0 < value <= ingest.MAX_CHUNK_TOKENS for value in tokens)
    assert min(tokens[:-1]) >= ingest.MIN_CHUNK_TOKENS
    assert any(
        " ".join(texts[index].split()[-12:]) in texts[index + 1]
        for index in range(len(texts) - 1)
    )


def test_embedding_file_must_cover_every_chunk(ingest, tmp_path):
    """FR-CORP-001: an embedding file missing a chunk id aborts the ingest."""
    manifest = make_manifest(tmp_path, make_source())
    pipeline = ingest.IngestPipeline(actor="qa-test")
    plan = pipeline.build_plan(manifest)
    first = plan.chunks[0]
    embedding_path = tmp_path / "embeddings.json"
    embedding_path.write_text(
        json.dumps({first.chunk_id: [0.0] * ingest.EMBEDDING_DIM}),
        encoding="utf-8",
    )

    with pytest.raises(ingest.IngestError, match="missing"):
        pipeline.load_embeddings(embedding_path, plan)


def test_embedding_dimension_mismatch_aborts(ingest, tmp_path):
    """FR-CORP-001: ADR-007 step 3 rejects vectors that do not match 1536 dims."""
    manifest = make_manifest(tmp_path, make_source())
    pipeline = ingest.IngestPipeline(actor="qa-test")
    plan = pipeline.build_plan(manifest)
    wrong = {
        chunk.chunk_id: [0.0] * (ingest.EMBEDDING_DIM - 1)
        for chunk in plan.chunks
    }
    embedding_path = tmp_path / "embeddings.json"
    embedding_path.write_text(json.dumps(wrong), encoding="utf-8")

    with pytest.raises(ingest.IngestError, match="1536"):
        pipeline.load_embeddings(embedding_path, plan)


def test_embeddings_are_written_as_pgvector_literals(ingest, tmp_path):
    """FR-CORP-001: supplied vectors become [..]::vector literals on insert."""
    manifest = make_manifest(tmp_path, make_source())
    pipeline = ingest.IngestPipeline(actor="qa-test")
    plan = pipeline.build_plan(manifest)
    vectors = {
        chunk.chunk_id: (0.5,) * ingest.EMBEDDING_DIM for chunk in plan.chunks
    }
    connection = FakeConnection()

    report = pipeline.execute(plan, connection=connection, embeddings=vectors)

    assert report.as_dict()["embeddings"] == "file"
    inserts = connection.statements("INSERT INTO content_chunks")
    assert inserts
    for _, params in inserts:
        assert params is not None
        literal = params[6]
        assert isinstance(literal, str)
        assert literal.startswith("[") and literal.endswith("]")
        assert literal.count(",") == ingest.EMBEDDING_DIM - 1


def test_runtime_role_is_rejected(ingest, tmp_path):
    """INV-SEC-001: ingestion refuses the read-only app_runtime role."""
    manifest = make_manifest(tmp_path, make_source())
    pipeline = ingest.IngestPipeline(actor="qa-test")
    plan = pipeline.build_plan(manifest)
    connection = FakeConnection(role="app_runtime")

    with pytest.raises(ingest.IngestError, match="app_runtime"):
        pipeline.execute(plan, connection=connection, embeddings={})

    assert connection.commits == 0
    assert connection.rollbacks == 0
    assert not connection.statements("INSERT")


def test_write_failure_rolls_back_everything(ingest, tmp_path):
    """FR-CORP-001: a failed write leaves no partial corpus (single transaction)."""
    manifest = make_manifest(tmp_path, make_source())
    pipeline = ingest.IngestPipeline(actor="qa-test")
    plan = pipeline.build_plan(manifest)
    connection = FakeConnection(fail_on="INSERT INTO content_chunks")

    with pytest.raises(RuntimeError, match="write failed"):
        pipeline.execute(plan, connection=connection, embeddings={})

    assert connection.commits == 0
    assert connection.rollbacks == 1


def test_retired_source_removes_its_chunks(ingest, tmp_path):
    """FR-CORP-001: demoting a source to retired deletes its retrievable chunks."""
    manifest = make_manifest(
        tmp_path,
        make_source(review_status="retired", sections=[]),
    )
    pipeline = ingest.IngestPipeline(actor="qa-test")
    plan = pipeline.build_plan(manifest)
    connection = FakeConnection(existing_chunks=3)

    report = pipeline.execute(plan, connection=connection, embeddings={})
    result = report.as_dict()["sources"][0]

    assert result["status"] == "retired"
    assert result["chunks_written"] == 0
    assert result["chunks_removed"] == 3
    assert connection.statements("DELETE FROM content_chunks")
    assert not connection.statements("INSERT INTO content_chunks")
    audit = connection.statements("INSERT INTO content_audit")
    assert [call[1][0] for call in audit if call[1]] == ["retire"]


def test_chunk_ids_are_deterministic(ingest, tmp_path):
    """INV-CITE-001: reruns produce identical chunk ids so citations stay stable."""
    manifest = make_manifest(tmp_path, make_source())
    pipeline = ingest.IngestPipeline(actor="qa-test")

    first = pipeline.build_plan(manifest)
    second = pipeline.build_plan(manifest)

    assert [chunk.chunk_id for chunk in first.chunks] == [
        chunk.chunk_id for chunk in second.chunks
    ]
    assert first.manifest_sha256 == second.manifest_sha256
    assert first.chunks[0].chunk_id == "a2-grammar-present-simple-001"
