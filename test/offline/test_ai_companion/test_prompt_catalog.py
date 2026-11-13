"""Offline tests for versioned prompt-file loading and ADR-006 budgets."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from backend.ai_companion.prompt_assembly import (
    PromptAssembler,
    PromptAssemblyRequest,
    PromptCatalog,
    PromptCatalogError,
    load_prompt_catalog,
)
from backend.contracts.ai_companion import INSUFFICIENT_EVIDENCE_PHRASE

REPO_ROOT = Path(__file__).resolve().parents[3]
PROMPT_PATH = REPO_ROOT / "prompts" / "prompt_v1.0.0.yaml"


def read_prompt_text() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def write_prompt(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "prompt_v1.0.0.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_loads_versioned_prompt_file() -> None:
    """ADR-005/ADR-006: the real prompt file is versioned and complete."""
    catalog = load_prompt_catalog(PROMPT_PATH)

    assert isinstance(catalog, PromptCatalog)
    assert catalog.version == "prompt_v1.0.0"
    assert catalog.identity_policy
    assert INSUFFICIENT_EVIDENCE_PHRASE in catalog.standing_constraints
    assert set(catalog.schemas) == {
        "conversation",
        "lesson_help",
        "writing_feedback",
    }
    assert catalog.schema_for("conversation").schema_id == "conversation.v1"
    assert catalog.schema_for("lesson_help").schema_id == "lesson_help.v1"
    assert (
        catalog.schema_for("writing_feedback").schema_id
        == "writing_feedback.v1"
    )
    assert "{code}" in catalog.repair_template
    assert "{error_path}" in catalog.repair_template
    assert "{detail}" in catalog.repair_template


def test_real_catalog_assembles_within_layer_caps() -> None:
    """NFR-COST-001 / ADR-006: the real prompt fits the fixed 1,500-token budget."""
    catalog = load_prompt_catalog(PROMPT_PATH)

    result = PromptAssembler().assemble(
        PromptAssemblyRequest(
            prompt_version=catalog.version,
            identity_policy=catalog.identity_policy,
            standing_constraints=catalog.standing_constraints,
            response_schema=catalog.schema_for("lesson_help").text,
            learner_profile="English, level A1.",
            resumable_state="stage=practice; attempt=0.",
            evidence=(),
            history=(),
            current_turn="Please explain the past tense.",
        )
    )

    assert result.token_count <= 1500
    assert result.metadata.prompt_version == "prompt_v1.0.0"


def test_loading_is_deterministic() -> None:
    """ADR-006: prompt loading is reproducible for evaluation replay."""
    first = load_prompt_catalog(PROMPT_PATH)
    second = load_prompt_catalog(PROMPT_PATH)

    assert first.version == second.version
    assert first.identity_policy == second.identity_policy
    assert first.standing_constraints == second.standing_constraints
    assert first.repair_template == second.repair_template
    assert dict(first.schemas) == dict(second.schemas)


def test_rejects_version_filename_mismatch(tmp_path: Path) -> None:
    """ADR-006: a prompt version cannot be silently reused under another name."""
    text = read_prompt_text().replace(
        "prompt_version: prompt_v1.0.0",
        "prompt_version: prompt_v1.0.1",
        1,
    )
    path = write_prompt(tmp_path, text)

    with pytest.raises(PromptCatalogError):
        load_prompt_catalog(path)


def test_rejects_unknown_prompt_key(tmp_path: Path) -> None:
    """ADR-005: an unknown prompt-file key is rejected, not ignored."""
    path = write_prompt(tmp_path, read_prompt_text() + "unknown_key: value\n")

    with pytest.raises(PromptCatalogError):
        load_prompt_catalog(path)


def test_rejects_malformed_prompt_block(tmp_path: Path) -> None:
    """Fail-closed: unsupported YAML syntax never becomes model input."""
    text = read_prompt_text().replace("identity_policy: |", "identity_policy: >", 1)
    path = write_prompt(tmp_path, text)

    with pytest.raises(PromptCatalogError):
        load_prompt_catalog(path)


def test_rejects_missing_abstention_phrase(tmp_path: Path) -> None:
    """ADR-005: the prompt and validator must share the exact abstention phrase."""
    text = read_prompt_text().replace(INSUFFICIENT_EVIDENCE_PHRASE, "No evidence.")
    path = write_prompt(tmp_path, text)

    with pytest.raises(PromptCatalogError):
        load_prompt_catalog(path)


def test_rejects_missing_repair_placeholder(tmp_path: Path) -> None:
    """ADR-005: a repair template must identify the rejection and error path."""
    text = read_prompt_text().replace("{code}", "code")
    path = write_prompt(tmp_path, text)

    with pytest.raises(PromptCatalogError):
        load_prompt_catalog(path)


def test_rejects_empty_identity_policy(tmp_path: Path) -> None:
    """ADR-006: an empty protected layer cannot be sent to the model."""
    text = re.sub(
        r"identity_policy: \|\r?\n(?:  .*\r?\n)+",
        "identity_policy: |\n",
        read_prompt_text(),
        count=1,
    )
    path = write_prompt(tmp_path, text)

    with pytest.raises(PromptCatalogError):
        load_prompt_catalog(path)
