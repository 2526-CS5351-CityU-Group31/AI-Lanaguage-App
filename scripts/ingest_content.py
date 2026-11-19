"""Ingest approved lesson content into the read-only pgvector corpus.

Element: IngestScript
Implements: ADR-007 (offline ingestion, published-only retrieval, audit trail);
  FR-CORP-001; INV-SEC-001 (ingestion uses a separate admin role while the
  runtime role stays SELECT-only); INV-CITE-001 (stable chunk ids are the
  citation unit).

This is an offline administrative command. The runtime application never
imports it and never reads ``ADMIN_DATABASE_URL``. The only environment
variable this script reads is ``ADMIN_DATABASE_URL``; it must never be set on
the Render web service.

Workflow
--------
1. Validate and chunk (no database access)::

       python scripts/ingest_content.py --manifest content/manifest.yaml --dry-run

   A dry-run report (``--report chunks.json``) contains the exact ``chunk_id``
   and ``text`` of every published chunk, which is the input for the embedding
   step.

2. Index. Without vectors the rows are written with ``embedding = NULL``
   (metadata-only retrieval until vectors are backfilled)::

       python scripts/ingest_content.py --manifest content/manifest.yaml

   With vectors, pass a JSON object mapping every ``chunk_id`` to a list of
   exactly ``EMBEDDING_DIM`` numbers::

       python scripts/ingest_content.py --manifest content/manifest.yaml \\
           --embedding-file embeddings.json --report reports/ingest.json

3. Demote or retire a source by setting ``review_status`` to ``draft`` or
   ``retired`` in the manifest. Its chunks are deleted in the same
   transaction. Omitting a source from the manifest does *not* delete it.

Manifest paths are resolved relative to the manifest file and may not escape
that directory. Requires PyYAML (already used by the other ``scripts/`` checks)
and psycopg for a real run.
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import math
import os
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = REPO_ROOT / "content" / "manifest.yaml"

ADMIN_DATABASE_URL_ENV = "ADMIN_DATABASE_URL"
EMBEDDING_DIM = 1536
MIN_CHUNK_TOKENS = 200
MAX_CHUNK_TOKENS = 400
MAX_OVERLAP_TOKENS = 40
CEFR_LEVELS = ("A1", "A2", "B1", "B2")
LANGUAGES = ("en",)
REVIEW_STATUSES = ("draft", "published", "retired")

SOURCE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{2,127}$")
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")

_TOP_LEVEL_KEYS = frozenset({"version", "sources"})
_SOURCE_KEYS = frozenset(
    {
        "source_id",
        "title",
        "language",
        "level",
        "topic",
        "review_status",
        "sections",
    }
)
_SECTION_KEYS = frozenset({"section", "text", "path"})


class IngestError(Exception):
    """FR-CORP-001: a validation or ingestion failure that aborts the run."""


# ---------------------------------------------------------------------------
# Plan model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Chunk:
    """One retrievable lesson section chunk (FR-CORP-001; ADR-007)."""

    chunk_id: str
    source_id: str
    section: str
    ordinal: int
    text: str
    token_count: int


@dataclass(frozen=True)
class Source:
    """One lesson source and its published chunks (FR-CORP-001)."""

    source_id: str
    title: str
    language: str
    level: str
    topic: str | None
    review_status: str
    chunks: tuple[Chunk, ...]


@dataclass(frozen=True)
class IngestPlan:
    """Validated, deterministic ingestion plan; no rows are written yet."""

    manifest_path: Path
    manifest_sha256: str
    sources: tuple[Source, ...]

    @property
    def chunks(self) -> tuple[Chunk, ...]:
        """INV-CITE-001: only published chunks are citable."""
        return tuple(
            chunk
            for source in self.sources
            if source.review_status == "published"
            for chunk in source.chunks
        )

    @property
    def planned_chunks(self) -> tuple[Chunk, ...]:
        """FR-CORP-001: every chunk a dry run can show for human review."""
        return tuple(chunk for source in self.sources for chunk in source.chunks)

    @property
    def published_sources(self) -> tuple[Source, ...]:
        """Return the sources whose chunks may be served."""
        return tuple(
            source for source in self.sources if source.review_status == "published"
        )


@dataclass(frozen=True)
class SourceResult:
    """Per-source outcome for the audit report."""

    source_id: str
    status: str
    chunks_planned: int
    chunks_written: int
    chunks_removed: int
    reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """Return the JSON-safe report entry (FR-CORP-001)."""
        return {
            "source_id": self.source_id,
            "status": self.status,
            "chunks_planned": self.chunks_planned,
            "chunks_written": self.chunks_written,
            "chunks_removed": self.chunks_removed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class IngestReport:
    """FR-CORP-001: audit report emitted by a dry-run or a real ingest."""

    manifest_path: str
    manifest_sha256: str
    generated_at: str
    actor: str
    dry_run: bool
    database_role: str | None
    embeddings: str
    published_sources: int
    skipped_sources: int
    sources: tuple[SourceResult, ...]
    planned_chunks: int
    chunks: int
    warnings: tuple[str, ...]
    chunk_plan: tuple[dict[str, Any], ...] | None = None

    def as_dict(self) -> dict[str, Any]:
        """Return the JSON-safe report payload (FR-CORP-001)."""
        payload: dict[str, Any] = {
            "status": "ok",
            "dry_run": self.dry_run,
            "manifest": self.manifest_path,
            "manifest_sha256": self.manifest_sha256,
            "generated_at": self.generated_at,
            "actor": self.actor,
            "database_role": self.database_role,
            "embeddings": self.embeddings,
            "published_sources": self.published_sources,
            "skipped_sources": self.skipped_sources,
            "planned_chunks": self.planned_chunks,
            "chunks": self.chunks,
            "sources": [source.as_dict() for source in self.sources],
            "warnings": list(self.warnings),
        }
        if self.chunk_plan is not None:
            payload["chunk_plan"] = list(self.chunk_plan)
        return payload


# ---------------------------------------------------------------------------
# Deterministic chunking
# ---------------------------------------------------------------------------


def estimate_tokens(text: str) -> int:
    """Return the ADR-006 deterministic token estimate (ceil(chars / 4))."""
    return math.ceil(len(text) / 4)


def clean_text(text: str) -> str:
    """Normalise whitespace without changing lesson wording (FR-CORP-001)."""
    normalised = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in normalised.split("\n")]
    cleaned: list[str] = []
    blank_lines = 0
    for line in lines:
        if line.strip():
            blank_lines = 0
            cleaned.append(line)
            continue
        blank_lines += 1
        if blank_lines <= 2:
            cleaned.append("")
    return "\n".join(cleaned).strip()


def _hard_split(unit: str, max_tokens: int) -> list[str]:
    """Split one oversized sentence on word boundaries (ADR-007 step 2)."""
    if estimate_tokens(unit) <= max_tokens:
        return [unit]
    max_chars = max_tokens * 4
    parts: list[str] = []
    current: list[str] = []
    size = 0
    for word in unit.split():
        if len(word) > max_chars:
            raise IngestError(
                "lesson text contains a single token longer than one chunk"
            )
        if current and size + 1 + len(word) > max_chars:
            parts.append(" ".join(current))
            current = []
            size = 0
        if current:
            size += 1
        current.append(word)
        size += len(word)
    if current:
        parts.append(" ".join(current))
    if any(estimate_tokens(part) > max_tokens for part in parts):
        raise IngestError("internal error: chunk exceeds the token ceiling")
    return parts


def _units(text: str) -> list[str]:
    """Split section text into sentences, then hard-split oversized ones."""
    sentences = [
        " ".join(part.split())
        for part in _SENTENCE_BOUNDARY.split(text)
        if part.strip()
    ]
    units: list[str] = []
    for sentence in sentences:
        units.extend(_hard_split(sentence, MAX_CHUNK_TOKENS))
    return units


def _tail(units: Sequence[str], max_tokens: int) -> list[str]:
    """Return the trailing units worth at most ``max_tokens`` (overlap cap)."""
    tail: list[str] = []
    for unit in reversed(units):
        candidate = [unit, *tail]
        if estimate_tokens(" ".join(candidate)) > max_tokens:
            break
        tail = candidate
    return tail


def chunk_text(text: str) -> list[str]:
    """Split text into 200-400 token chunks with at most 10% overlap.

    Implements: ADR-007 step 2 (200-400 token sections, overlap <= 10%).
    A short final chunk is allowed so the last sentence is never dropped.
    Token counts are measured on the joined text so inter-unit spaces are
    never omitted from the ceiling check.
    """
    units = _units(text)
    chunks: list[str] = []
    current: list[str] = []
    for unit in units:
        if current:
            candidate = " ".join([*current, unit])
            if estimate_tokens(candidate) > MAX_CHUNK_TOKENS:
                chunks.append(" ".join(current))
                carry = _tail(current, MAX_OVERLAP_TOKENS)
                joined = " ".join([*carry, unit])
                if carry and estimate_tokens(joined) <= MAX_CHUNK_TOKENS:
                    current = list(carry)
                else:
                    current = []
        current.append(unit)
    if current:
        chunks.append(" ".join(current))
    return [chunk for chunk in chunks if chunk.strip()]


# ---------------------------------------------------------------------------
# Manifest validation
# ---------------------------------------------------------------------------


class _Errors:
    """Collect validation errors so one run reports every problem."""

    def __init__(self) -> None:
        self.messages: list[str] = []

    def add(self, message: str) -> None:
        """Record one validation failure."""
        self.messages.append(message)

    def raise_if_any(self) -> None:
        """Abort with a single, actionable message."""
        if self.messages:
            raise IngestError("; ".join(self.messages))


def _mapping(value: Any, where: str, errors: _Errors) -> Mapping[str, Any]:
    """Return ``value`` as a mapping or record a validation error."""
    if not isinstance(value, dict):
        errors.add(f"{where} must be a mapping")
        return {}
    return value


def _list(value: Any, where: str, errors: _Errors) -> list[Any]:
    """Return ``value`` as a list or record a validation error."""
    if not isinstance(value, list):
        errors.add(f"{where} must be a list")
        return []
    return value


def _non_empty_text(value: Any, where: str, errors: _Errors) -> str:
    """Return a non-empty stripped string or record a validation error."""
    if not isinstance(value, str) or not value.strip():
        errors.add(f"{where} must be non-empty text")
        return ""
    return value.strip()


def _reject_unknown_keys(
    mapping: Mapping[str, Any],
    allowed: frozenset[str],
    where: str,
    errors: _Errors,
) -> None:
    """ADR-007: fail closed on unknown manifest fields."""
    unknown = sorted(set(mapping) - allowed)
    if unknown:
        errors.add(f"{where} has unknown field(s): {', '.join(unknown)}")


def _section_text(
    section: Mapping[str, Any],
    *,
    manifest_dir: Path,
    where: str,
    errors: _Errors,
) -> str:
    """Resolve inline text or a file path for one section."""
    has_text = "text" in section
    has_path = "path" in section
    if has_text == has_path:
        errors.add(f"{where} must define exactly one of 'text' or 'path'")
        return ""
    if has_text:
        return clean_text(
            _non_empty_text(section["text"], f"{where}.text", errors)
        )

    raw_path = _non_empty_text(section["path"], f"{where}.path", errors)
    if not raw_path:
        return ""
    candidate = (manifest_dir / raw_path).resolve()
    if not candidate.is_relative_to(manifest_dir.resolve()):
        errors.add(f"{where}.path escapes the manifest directory")
        return ""
    try:
        return clean_text(candidate.read_text(encoding="utf-8"))
    except (OSError, UnicodeError):
        errors.add(f"{where}.path cannot be read as UTF-8 text")
        return ""


def _build_source(
    raw: Mapping[str, Any],
    *,
    index: int,
    manifest_dir: Path,
    errors: _Errors,
) -> Source | None:
    """Validate one source and build its published chunks."""
    where = f"sources[{index}]"
    _reject_unknown_keys(raw, _SOURCE_KEYS, where, errors)

    source_id = _non_empty_text(raw.get("source_id"), f"{where}.source_id", errors)
    if source_id and not SOURCE_ID_PATTERN.match(source_id):
        errors.add(
            f"{where}.source_id must match {SOURCE_ID_PATTERN.pattern}"
        )
    title = _non_empty_text(raw.get("title"), f"{where}.title", errors)

    language = _non_empty_text(raw.get("language"), f"{where}.language", errors)
    if language and language not in LANGUAGES:
        errors.add(f"{where}.language must be 'en'")

    level = _non_empty_text(raw.get("level"), f"{where}.level", errors)
    if level and level not in CEFR_LEVELS:
        errors.add(f"{where}.level must be one of {', '.join(CEFR_LEVELS)}")

    topic_value = raw.get("topic")
    topic: str | None = None
    if topic_value is not None:
        topic = _non_empty_text(topic_value, f"{where}.topic", errors)

    review_status = _non_empty_text(
        raw.get("review_status"), f"{where}.review_status", errors
    )
    if review_status and review_status not in REVIEW_STATUSES:
        errors.add(
            f"{where}.review_status must be one of {', '.join(REVIEW_STATUSES)}"
        )

    raw_sections = raw.get("sections", [])
    sections = _list(raw_sections, f"{where}.sections", errors)
    if review_status == "published" and not sections:
        errors.add(f"{where}.sections must not be empty for a published source")

    chunks: list[Chunk] = []
    seen_sections: set[str] = set()
    ordinal = 0
    for section_index, raw_section in enumerate(sections):
        section_where = f"{where}.sections[{section_index}]"
        section = _mapping(raw_section, section_where, errors)
        if not section:
            continue
        _reject_unknown_keys(section, _SECTION_KEYS, section_where, errors)
        section_name = _non_empty_text(
            section.get("section"), f"{section_where}.section", errors
        )
        if section_name and section_name in seen_sections:
            errors.add(f"{section_where}.section is duplicated in this source")
        seen_sections.add(section_name)

        text = _section_text(
            section,
            manifest_dir=manifest_dir,
            where=section_where,
            errors=errors,
        )
        if not text:
            continue
        for chunk_body in chunk_text(text):
            ordinal += 1
            token_count = estimate_tokens(chunk_body)
            if token_count <= 0 or token_count > MAX_CHUNK_TOKENS:
                errors.add(
                    f"{section_where} produced a chunk outside 1..{MAX_CHUNK_TOKENS} tokens"
                )
                continue
            chunks.append(
                Chunk(
                    chunk_id=f"{source_id}-{ordinal:03d}",
                    source_id=source_id,
                    section=section_name,
                    ordinal=ordinal,
                    text=chunk_body,
                    token_count=token_count,
                )
            )

    if not source_id or not title or not language or not level or not review_status:
        return None

    # Drafts are chunked too so a dry run can show the reviewer exactly what
    # would be published. Only ``IngestPlan.chunks`` (published) is ever
    # written, embedded or citable (ADR-007, INV-CITE-001).
    return Source(
        source_id=source_id,
        title=title,
        language=language,
        level=level,
        topic=topic,
        review_status=review_status,
        chunks=tuple(chunks),
    )


def load_manifest(manifest_path: str | Path) -> tuple[Path, str, tuple[Source, ...]]:
    """Read and validate a manifest, returning sources and its digest.

    Implements: FR-CORP-001; ADR-007 step 1 (dry run validates fields,
    duplicates, language and empty text).
    """
    path = Path(manifest_path)
    try:
        raw_bytes = path.read_bytes()
    except OSError as exc:
        raise IngestError(f"cannot read manifest {path}") from exc
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise IngestError(f"manifest {path} is not UTF-8") from exc
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise IngestError(f"manifest {path} is not valid YAML: {exc}") from exc

    errors = _Errors()
    document = _mapping(data, "manifest", errors)
    _reject_unknown_keys(document, _TOP_LEVEL_KEYS, "manifest", errors)

    version = document.get("version")
    if isinstance(version, bool) or not isinstance(version, int) or version != 1:
        errors.add("manifest.version must be 1")

    raw_sources = _list(document.get("sources"), "manifest.sources", errors)
    if not raw_sources:
        errors.add("manifest.sources must contain at least one source")

    manifest_dir = path.resolve().parent
    sources: list[Source] = []
    seen_ids: set[str] = set()
    for index, raw_source in enumerate(raw_sources):
        source = _build_source(
            _mapping(raw_source, f"sources[{index}]", errors),
            index=index,
            manifest_dir=manifest_dir,
            errors=errors,
        )
        if source is None:
            continue
        if source.source_id in seen_ids:
            errors.add(f"sources[{index}].source_id is duplicated")
            continue
        seen_ids.add(source.source_id)
        sources.append(source)

    chunk_ids = [chunk.chunk_id for source in sources for chunk in source.chunks]
    if len(chunk_ids) != len(set(chunk_ids)):
        errors.add("manifest produces duplicate chunk ids")

    errors.raise_if_any()
    digest = hashlib.sha256(raw_bytes).hexdigest()
    return path.resolve(), digest, tuple(sources)


# ---------------------------------------------------------------------------
# Embeddings and pgvector serialisation
# ---------------------------------------------------------------------------


def _validate_embeddings(
    plan: IngestPlan,
    vectors: Mapping[str, Sequence[float]],
    *,
    embedding_dim: int,
) -> dict[str, tuple[float, ...]]:
    """ADR-007 step 3: every chunk has one vector of the index dimension."""
    expected = {chunk.chunk_id for chunk in plan.chunks}
    supplied = set(vectors)
    errors = _Errors()
    missing = sorted(expected - supplied)
    extra = sorted(supplied - expected)
    if missing:
        errors.add(f"embedding file is missing {len(missing)} chunk id(s)")
    if extra:
        errors.add(f"embedding file has {len(extra)} unknown chunk id(s)")

    validated: dict[str, tuple[float, ...]] = {}
    for chunk_id in sorted(expected & supplied):
        vector = vectors[chunk_id]
        if not isinstance(vector, (list, tuple)):
            errors.add(f"embedding for {chunk_id} must be a list")
            continue
        if len(vector) != embedding_dim:
            errors.add(
                f"embedding for {chunk_id} must have exactly {embedding_dim} dimensions"
            )
            continue
        numbers: list[float] = []
        for value in vector:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                errors.add(f"embedding for {chunk_id} contains a non-numeric value")
                break
            number = float(value)
            if not math.isfinite(number):
                errors.add(f"embedding for {chunk_id} contains a non-finite value")
                break
            numbers.append(number)
        else:
            validated[chunk_id] = tuple(numbers)

    errors.raise_if_any()
    return validated


def vector_literal(vector: Sequence[float]) -> str:
    """Return a pgvector text literal, e.g. ``[0.1,0.2]`` (ADR-007)."""
    return "[" + ",".join(repr(float(value)) for value in vector) + "]"


def load_embedding_file(
    path: str | Path,
    plan: IngestPlan,
    *,
    embedding_dim: int,
) -> dict[str, tuple[float, ...]]:
    """Read a ``{chunk_id: [float, ...]}`` JSON map and validate it.

    Implements: FR-CORP-001; ADR-007 step 3 (embedding dimension check).
    """
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise IngestError(f"cannot read embedding file {path}") from exc
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise IngestError(f"embedding file {path} is not valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise IngestError("embedding file must be a JSON object")
    return _validate_embeddings(plan, payload, embedding_dim=embedding_dim)


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------


def _default_actor() -> str:
    """Return a best-effort operator name for the audit row (FR-CORP-001)."""
    try:
        return getpass.getuser() or "unknown"
    except (KeyError, OSError):  # pragma: no cover - defensive
        return "unknown"


def _chunk_plan(plan: IngestPlan) -> tuple[dict[str, Any], ...]:
    """Return the dry-run chunk listing used for review (FR-CORP-001)."""
    status_by_source = {
        source.source_id: source.review_status for source in plan.sources
    }
    return tuple(
        {
            "chunk_id": chunk.chunk_id,
            "source_id": chunk.source_id,
            "section": chunk.section,
            "ordinal": chunk.ordinal,
            "token_count": chunk.token_count,
            "review_status": status_by_source[chunk.source_id],
            "text": chunk.text,
        }
        for chunk in plan.planned_chunks
    )


def _warnings_for(plan: IngestPlan, *, vectors: bool) -> tuple[str, ...]:
    """Return non-fatal observations for the report (FR-CORP-001)."""
    warnings: list[str] = []
    if plan.chunks and not vectors:
        warnings.append(
            "no embeddings supplied: rows are written with embedding=NULL until "
            "vectors are backfilled (metadata-only retrieval)"
        )
    short = [
        chunk
        for chunk in plan.planned_chunks
        if chunk.token_count < MIN_CHUNK_TOKENS
    ]
    if short:
        warnings.append(
            f"{len(short)} chunk(s) are shorter than {MIN_CHUNK_TOKENS} tokens"
        )
    skipped = [source for source in plan.sources if source.review_status != "published"]
    if skipped:
        warnings.append(
            f"{len(skipped)} source(s) are not published; their chunks are not served"
        )
    return tuple(warnings)


class IngestPipeline:
    """Validate, chunk, embed and transactionally index approved lessons.

    Implements: FR-CORP-001; ADR-007; INV-SEC-001 (refuses the runtime role);
    INV-CITE-001 (deterministic chunk ids).
    """

    def __init__(self, *, embedding_dim: int = EMBEDDING_DIM, actor: str | None = None):
        """Store the pinned index dimension and the audit actor (FR-CORP-001)."""
        self._embedding_dim = embedding_dim
        self._actor = actor or _default_actor()

    @property
    def embedding_dim(self) -> int:
        """Return the pinned embedding dimension (ADR-007)."""
        return self._embedding_dim

    def build_plan(self, manifest_path: str | Path) -> IngestPlan:
        """Validate a manifest and return a deterministic plan (FR-CORP-001)."""
        path, digest, sources = load_manifest(manifest_path)
        return IngestPlan(
            manifest_path=path,
            manifest_sha256=digest,
            sources=sources,
        )

    def load_embeddings(
        self, path: str | Path, plan: IngestPlan
    ) -> dict[str, tuple[float, ...]]:
        """Validate and load the optional embedding file (FR-CORP-001)."""
        return load_embedding_file(path, plan, embedding_dim=self._embedding_dim)

    def execute(
        self,
        plan: IngestPlan,
        *,
        connection: Any | None = None,
        embeddings: Mapping[str, Sequence[float]] | None = None,
        dry_run: bool = False,
    ) -> IngestReport:
        """Apply the plan, returning an audit report.

        Implements: FR-CORP-001; ADR-007 step 3 (transactional index and
        validation); INV-SEC-001 (runtime role is rejected).
        """
        vectors: dict[str, tuple[float, ...]] = {}
        if embeddings:
            vectors = _validate_embeddings(
                plan, embeddings, embedding_dim=self._embedding_dim
            )

        published = len(plan.published_sources)
        skipped = len(plan.sources) - published
        warnings = _warnings_for(plan, vectors=bool(vectors))
        generated_at = datetime.now(UTC).isoformat()

        if dry_run:
            results = tuple(
                SourceResult(
                    source_id=source.source_id,
                    status="planned" if source.review_status == "published" else "skipped",
                    chunks_planned=len(source.chunks),
                    chunks_written=0,
                    chunks_removed=0,
                    reason=(
                        None
                        if source.review_status == "published"
                        else f"review_status={source.review_status}"
                    ),
                )
                for source in plan.sources
            )
            return IngestReport(
                manifest_path=str(plan.manifest_path),
                manifest_sha256=plan.manifest_sha256,
                generated_at=generated_at,
                actor=self._actor,
                dry_run=True,
                database_role=None,
                embeddings="file" if vectors else "none",
                published_sources=published,
                skipped_sources=skipped,
                sources=results,
                planned_chunks=len(plan.planned_chunks),
                chunks=len(plan.chunks),
                warnings=warnings,
                chunk_plan=_chunk_plan(plan),
            )

        if connection is None:
            raise IngestError("a database connection is required for a real ingest")

        role = _current_user(connection)
        if role == "app_runtime":
            raise IngestError(
                "refusing to ingest with the read-only app_runtime role "
                "(INV-SEC-001); use the offline admin DSN"
            )

        results = []
        try:
            for source in plan.sources:
                results.append(self._write_source(connection, source, vectors))
            connection.commit()
        except Exception:
            connection.rollback()
            raise

        return IngestReport(
            manifest_path=str(plan.manifest_path),
            manifest_sha256=plan.manifest_sha256,
            generated_at=generated_at,
            actor=self._actor,
            dry_run=False,
            database_role=role,
            embeddings="file" if vectors else "none",
            published_sources=published,
            skipped_sources=skipped,
            sources=tuple(results),
            planned_chunks=len(plan.planned_chunks),
            chunks=len(plan.chunks),
            warnings=warnings,
        )

    def _write_source(
        self,
        connection: Any,
        source: Source,
        vectors: Mapping[str, tuple[float, ...]],
    ) -> SourceResult:
        """Upsert one source, replace its chunks, append audit (FR-CORP-001)."""
        connection.execute(
            """
            INSERT INTO content_sources
                (source_id, title, language, level, topic, review_status)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (source_id) DO UPDATE SET
                title = EXCLUDED.title,
                language = EXCLUDED.language,
                level = EXCLUDED.level,
                topic = EXCLUDED.topic,
                review_status = EXCLUDED.review_status
            """,
            (
                source.source_id,
                source.title,
                source.language,
                source.level,
                source.topic,
                source.review_status,
            ),
        )
        removed_rows = connection.execute(
            "DELETE FROM content_chunks WHERE source_id = %s RETURNING chunk_id",
            (source.source_id,),
        ).fetchall()
        removed = len(removed_rows)

        if source.review_status == "published":
            for chunk in source.chunks:
                vector = vectors.get(chunk.chunk_id)
                connection.execute(
                    """
                    INSERT INTO content_chunks
                        (chunk_id, source_id, section, ordinal, text,
                         token_count, embedding)
                    VALUES (%s, %s, %s, %s, %s, %s, %s::vector)
                    """,
                    (
                        chunk.chunk_id,
                        chunk.source_id,
                        chunk.section,
                        chunk.ordinal,
                        chunk.text,
                        chunk.token_count,
                        vector_literal(vector) if vector is not None else None,
                    ),
                )
            event = "ingest"
            status = "ingested"
            written = len(source.chunks)
            reason = None
        else:
            event = "retire" if source.review_status == "retired" else "skip"
            status = "retired" if source.review_status == "retired" else "skipped"
            written = 0
            reason = f"review_status={source.review_status}"

        connection.execute(
            "INSERT INTO content_audit (event, source_id, actor) VALUES (%s, %s, %s)",
            (event, source.source_id, self._actor),
        )
        return SourceResult(
            source_id=source.source_id,
            status=status,
            chunks_planned=len(source.chunks),
            chunks_written=written,
            chunks_removed=removed,
            reason=reason,
        )


def _current_user(connection: Any) -> str:
    """Return the connected role, refusing the runtime role (INV-SEC-001)."""
    row = connection.execute("SELECT current_user").fetchone()
    if not row:
        raise IngestError("cannot determine the connected database role")
    return str(row[0])


def _connect(dsn: str) -> Any:
    """Open the admin connection without printing it (INV-SEC-001)."""
    try:
        import psycopg
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise IngestError("psycopg is required for a non-dry run") from exc
    try:
        return psycopg.connect(
            dsn,
            connect_timeout=15,
            application_name="ai-companion-ingest",
        )
    except Exception as exc:
        raise IngestError("cannot connect to the admin database") from exc


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    """Build the offline admin CLI (FR-CORP-001)."""
    parser = argparse.ArgumentParser(
        description=(
            "Validate, chunk, embed and transactionally index approved lesson "
            "content (FR-CORP-001)."
        ),
        epilog=(
            "ADMIN_DATABASE_URL is required only for a real run and must never "
            "be exposed to the Render service. Without --embedding-file, rows "
            "are written with embedding=NULL (metadata-only retrieval). "
            "Omitting a source does not delete it; set review_status=retired."
        ),
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help="path to the lesson manifest (default: content/manifest.yaml)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate and chunk without connecting to the database",
    )
    parser.add_argument(
        "--embedding-file",
        type=Path,
        help="JSON object mapping every chunk_id to 1536 floats",
    )
    parser.add_argument(
        "--report",
        type=Path,
        help="write the JSON audit report to this path instead of stdout",
    )
    parser.add_argument(
        "--actor",
        help="operator name recorded in content_audit (default: OS user)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the admin command; return a process exit code.

    Implements: FR-CORP-001; ADR-007 step 1/2/3.
    """
    args = _build_parser().parse_args(argv)
    pipeline = IngestPipeline(actor=args.actor)
    try:
        plan = pipeline.build_plan(args.manifest)
        vectors = (
            pipeline.load_embeddings(args.embedding_file, plan)
            if args.embedding_file
            else {}
        )
        if args.dry_run:
            report = pipeline.execute(plan, embeddings=vectors, dry_run=True)
        else:
            dsn = os.environ.get(ADMIN_DATABASE_URL_ENV, "").strip()
            if not dsn:
                raise IngestError(
                    f"{ADMIN_DATABASE_URL_ENV} is required for a real ingest"
                )
            connection = _connect(dsn)
            try:
                report = pipeline.execute(
                    plan, connection=connection, embeddings=vectors
                )
            finally:
                connection.close()
    except IngestError as exc:
        print(f"ingest_content: {exc}", file=sys.stderr)
        return 2

    payload = report.as_dict()
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        action = "planned" if report.dry_run else "wrote"
        count = report.planned_chunks if report.dry_run else report.chunks
        print(
            f"ingest_content: {action} {count} chunk(s) from "
            f"{len(report.sources)} source(s); report: {args.report}"
        )
    else:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
