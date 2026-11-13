"""Offline boundary tests for the AI companion foundation."""

from __future__ import annotations

import ast
import socket
from pathlib import Path
import pytest

from backend.ai_companion.prompt_assembly import PromptAssembler
from backend.ai_companion.rag_pipeline import RagPipeline, RagRequest
from backend.ai_companion.retrieval_adapter import RetrievalAdapter
from backend.ai_companion.tutor import Tutor
from backend.contracts.ai_companion import ModelResponse, ValidationVerdict

from fakes import FakeModelGateway, FakeResponseValidator, FakeRetrievalService

REPO_ROOT = Path(__file__).resolve().parents[3]
FOUNDATION_FILES = (
    REPO_ROOT / "src/backend/contracts/ai_companion.py",
    REPO_ROOT / "src/backend/ai_companion/prompt_assembly.py",
    REPO_ROOT / "src/backend/ai_companion/retrieval_adapter.py",
    REPO_ROOT / "src/backend/ai_companion/tutor.py",
    REPO_ROOT / "src/backend/ai_companion/rag_pipeline.py",
)
PROMPT_LOADING_FILE = REPO_ROOT / "src/backend/ai_companion/prompt_assembly.py"

FORBIDDEN_ROOTS = {
    "anthropic",
    "fastapi",
    "httpx",
    "openai",
    "psycopg",
    "psycopg2",
    "pydantic",
    "requests",
    "sqlalchemy",
}
FORBIDDEN_MODULE_PREFIXES = (
    "backend.api",
    "backend.auth",
    "backend.database",
    "backend.grammar",
    "backend.safety_boundary",
    "backend.user_progress",
    "backend.vocabulary",
    "scripts",
)


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text())


def test_ai_foundation_imports_are_bounded() -> None:
    """ADR-001 / C3: the foundation imports no DB, API, provider, or safety module."""
    for path in FOUNDATION_FILES:
        tree = _parse(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    assert root not in FORBIDDEN_ROOTS, (path, alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                module = node.module
                assert module.split(".")[0] not in FORBIDDEN_ROOTS, (path, module)
                assert not module.startswith(FORBIDDEN_MODULE_PREFIXES), (path, module)


def test_ai_foundation_has_no_environment_or_ambient_file_io() -> None:
    """ADR-006 / S5: no environment reads or ambient filesystem access.

    The prompt catalog is the one intentional file read; it accepts an explicit
    path supplied by composition and never discovers paths from the environment.
    """
    for path in FOUNDATION_FILES:
        tree = _parse(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                assert node.id not in {"open", "getenv"}, (path, node.id)
            if isinstance(node, ast.Attribute):
                assert node.attr not in {"environ", "getenv"}, (path, node.attr)
    prompt_tree = _parse(PROMPT_LOADING_FILE)
    for node in ast.walk(prompt_tree):
        if isinstance(node, ast.Name):
            assert node.id != "open", (PROMPT_LOADING_FILE, node.id)


def _request() -> RagRequest:
    return RagRequest(
        request_id="req-boundary",
        task="conversation",
        prompt_version="prompt_v1.0.0",
        identity_policy="POLICY-MARKER",
        standing_constraints="CONSTRAINTS-MARKER",
        response_schema="SCHEMA-MARKER",
        schema_id="conversation.v1",
        learner_profile="PROFILE-MARKER",
        resumable_state="STATE-MARKER",
        history=(),
        current_turn="CURRENT-MARKER",
        requires_grounding=False,
        query="",
        language="en",
        level="A1",
        topic=None,
        top_k=5,
    )


def test_no_network_calls_during_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    """ADR-001: the offline pipeline performs no network access."""
    def fail_connect(*args: object, **kwargs: object) -> None:
        raise AssertionError("network access attempted by the AI foundation")

    monkeypatch.setattr(socket.socket, "connect", fail_connect)
    gateway = FakeModelGateway(
        responses=[
            ModelResponse(
                text='{"answer": "ok"}',
                model_id="stub-model-v1",
                prompt_tokens=10,
                completion_tokens=2,
            )
        ]
    )
    validator = FakeResponseValidator(
        verdicts=[
            ValidationVerdict(
                accepted=True,
                code="accepted",
                validated_text="ok",
            )
        ]
    )
    pipeline = RagPipeline(
        retrieval=RetrievalAdapter(
            FakeRetrievalService(chunks=())
        ),
        assembler=PromptAssembler(),
        tutor=Tutor(gateway),
        validator=validator,
    )

    result = pipeline.handle(_request())

    assert result.status == "accepted"
    assert result.prompt_tokens <= 1500
