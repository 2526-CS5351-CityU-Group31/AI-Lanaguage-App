"""CitationValidator - authoritative schema, citation and abstention gate.

Element: CitationValidator
Implements: ADR-005 §Response contracts and §Rejection codes; ADR-007 §Decision;
INV-CITE-001, NFR-QUAL-003, FR-CHAT-001, FR-FEED-001.

The validator is a pure function over model output and the retrieved published
evidence set. It never calls a model, the network, the database or an advisory
module. Invalid output becomes a typed verdict; the only path to learner-visible
text is ``accepted=True``.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from backend.contracts.ai_companion import (
    INSUFFICIENT_EVIDENCE_PHRASE,
    MAX_ANSWER_CHARS,
    MAX_EXAMPLE_CHARS,
    MAX_EXAMPLES,
    MAX_EXPLANATION_CHARS,
    MAX_FOLLOW_UP_CHARS,
    MAX_RAW_OUTPUT_CHARS,
    MAX_SOURCE_IDS,
    MAX_SUGGESTED_TEXT_CHARS,
    MAX_TIP_CHARS,
    MAX_TIPS,
    EvidenceSet,
    TaskType,
    ValidatedResponse,
    ValidationCode,
    ValidationVerdict,
    WritingFeedback,
)

TASKS: frozenset[str] = frozenset(
    ("conversation", "lesson_help", "writing_feedback")
)
COMMON_FIELDS: frozenset[str] = frozenset(
    ("task", "abstained", "source_ids", "answer", "follow_up", "tips")
)
WRITING_FIELDS: frozenset[str] = frozenset(
    ("suggested_text", "explanation", "examples")
)
TOOL_FIELDS: frozenset[str] = frozenset(
    (
        "tool",
        "tools",
        "tool_call",
        "tool_calls",
        "function",
        "functions",
        "function_call",
        "function_calls",
        "role",
        "system",
        "system_prompt",
        "url",
    )
)

_UNSAFE_MARKUP_PATTERNS = (
    re.compile(r"<\s*[/!]?\s*[A-Za-z]"),
    re.compile(r"(?i)\b(?:https?://|www\.|javascript:|data:)"),
    re.compile(r"!?\[[^\]]*\]\([^)]*\)"),
)


class _DuplicateKeyError(ValueError):
    """ADR-005 §Rejection codes: duplicate JSON keys are schema-invalid."""

    def __init__(self, key: str) -> None:
        super().__init__(key)
        self.key = key


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError(key)
        result[key] = value
    return result


def _reject_json_constant(value: str) -> Any:
    raise ValueError(f"non-finite JSON constant {value}")


def _validation_id(task: TaskType, raw_output: str, evidence: EvidenceSet) -> str:
    """Return a deterministic server-assigned validation id (ADR-005)."""
    published = "\x1f".join(evidence.published_ids)
    withheld = "\x1f".join(evidence.unpublished_ids)
    material = f"{task}\x1e{raw_output}\x1e{published}\x1e{withheld}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


def _reject(
    validation_id: str,
    code: ValidationCode,
    *,
    path: str = "",
    detail: str = "",
    repairable: bool = False,
) -> ValidationVerdict:
    return ValidationVerdict(
        accepted=False,
        code=code,
        repairable=repairable,
        error_path=path,
        detail=detail,
        validation_id=validation_id,
    )


def _has_unsafe_markup(text: str) -> bool:
    """ADR-005 §Common envelope: markdown allowlist only; no raw HTML or URLs."""
    return any(pattern.search(text) is not None for pattern in _UNSAFE_MARKUP_PATTERNS)


def _mentions_chunk_id(text: str, chunk_id: str) -> bool:
    """ADR-005: detect a citation token without matching a longer identifier."""
    if not chunk_id:
        return False
    pattern = re.compile(
        rf"(?<![A-Za-z0-9_]){re.escape(chunk_id)}(?![A-Za-z0-9_])"
    )
    return pattern.search(text) is not None


def _chunk_id_family_pattern(chunk_id: str) -> re.Pattern[str] | None:
    """ADR-005: match an invented id that shares a known id's numeric shape."""
    if not chunk_id:
        return None
    parts = re.split(r"(\d+)", chunk_id)
    body = "".join(
        r"\d+" if part.isdigit() else re.escape(part)
        for part in parts
        if part
    )
    if not body:
        return None
    return re.compile(rf"(?<![A-Za-z0-9_]){body}(?![A-Za-z0-9_])")


class CitationValidator:
    """ADR-005: pure authoritative gate for all tutor/model output."""

    def validate(
        self,
        task: TaskType,
        raw_output: str,
        evidence: EvidenceSet,
    ) -> ValidationVerdict:
        """Validate one model proposal against the response contract.

        Implements: ADR-005 §Response contracts and §Rejection codes;
        INV-CITE-001, NFR-QUAL-003.

        Validation order is safety-first: tool/role fields and citation or
        abstention failures are decided before repairable length/markup errors,
        so a response containing an invented citation can never be repaired.
        """
        validation_id = _validation_id(task, raw_output, evidence)

        if not isinstance(task, str) or task not in TASKS:
            return _reject(
                validation_id,
                "schema_invalid",
                path="task",
                detail="unknown task",
            )
        if not isinstance(raw_output, str) or not raw_output.strip():
            return _reject(
                validation_id,
                "schema_invalid",
                path="$",
                detail="empty output",
            )
        if len(raw_output) > MAX_RAW_OUTPUT_CHARS:
            return _reject(
                validation_id,
                "over_length",
                path="$",
                detail=f"raw output exceeds {MAX_RAW_OUTPUT_CHARS} characters",
            )

        try:
            parsed = json.loads(
                raw_output,
                object_pairs_hook=_no_duplicates,
                parse_constant=_reject_json_constant,
            )
        except _DuplicateKeyError as exc:
            return _reject(
                validation_id,
                "schema_invalid",
                path="$",
                detail=f"duplicate JSON key {exc.key!r}",
                repairable=True,
            )
        except (json.JSONDecodeError, ValueError):
            return _reject(
                validation_id,
                "schema_invalid",
                path="$",
                detail="output is not valid JSON",
                repairable=True,
            )
        except Exception:
            return _reject(
                validation_id,
                "schema_invalid",
                path="$",
                detail="output could not be parsed safely",
            )

        if not isinstance(parsed, dict):
            return _reject(
                validation_id,
                "schema_invalid",
                path="$",
                detail="output must be a JSON object",
                repairable=True,
            )
        data: dict[str, object] = {str(key): value for key, value in parsed.items()}

        tool_keys = sorted(TOOL_FIELDS.intersection(data))
        if tool_keys:
            return _reject(
                validation_id,
                "tool_request",
                path=tool_keys[0],
                detail="tool, function, role and URL fields are forbidden",
            )

        for field in ("task", "abstained", "source_ids", "answer"):
            if field not in data:
                return _reject(
                    validation_id,
                    "schema_invalid",
                    path=field,
                    detail="required field missing",
                    repairable=True,
                )

        task_value = data["task"]
        if not isinstance(task_value, str) or task_value not in TASKS:
            return _reject(
                validation_id,
                "schema_invalid",
                path="task",
                detail="task must be a supported enum value",
                repairable=True,
            )
        if task_value != task:
            return _reject(
                validation_id,
                "schema_invalid",
                path="task",
                detail="task does not match the requested task",
                repairable=True,
            )

        abstained_value = data["abstained"]
        if type(abstained_value) is not bool:
            return _reject(
                validation_id,
                "schema_invalid",
                path="abstained",
                detail="abstained must be a boolean",
                repairable=True,
            )
        abstained = bool(abstained_value)

        source_ids_value = data["source_ids"]
        if not isinstance(source_ids_value, list):
            return _reject(
                validation_id,
                "schema_invalid",
                path="source_ids",
                detail="source_ids must be an array of strings",
                repairable=True,
            )
        source_ids_list: list[str] = []
        for index, value in enumerate(source_ids_value):
            if not isinstance(value, str) or not value.strip():
                return _reject(
                    validation_id,
                    "schema_invalid",
                    path=f"source_ids[{index}]",
                    detail="source id must be a non-empty string",
                    repairable=True,
                )
            source_ids_list.append(value)
        source_ids = tuple(source_ids_list)

        answer_value = data["answer"]
        if not isinstance(answer_value, str) or not answer_value.strip():
            return _reject(
                validation_id,
                "schema_invalid",
                path="answer",
                detail="answer must be non-empty text",
                repairable=True,
            )
        answer = answer_value

        follow_up_value = data.get("follow_up")
        if follow_up_value is not None and not isinstance(follow_up_value, str):
            return _reject(
                validation_id,
                "schema_invalid",
                path="follow_up",
                detail="follow_up must be text when present",
                repairable=True,
            )
        follow_up = follow_up_value if isinstance(follow_up_value, str) else None

        tips_value = data.get("tips")
        tips_list: list[str] = []
        if tips_value is not None:
            if not isinstance(tips_value, list):
                return _reject(
                    validation_id,
                    "schema_invalid",
                    path="tips",
                    detail="tips must be an array of strings",
                    repairable=True,
                )
            for index, value in enumerate(tips_value):
                if not isinstance(value, str):
                    return _reject(
                        validation_id,
                        "schema_invalid",
                        path=f"tips[{index}]",
                        detail="tip must be text",
                        repairable=True,
                    )
                tips_list.append(value)
        tips = tuple(tips_list)

        writing: WritingFeedback | None = None
        if task == "writing_feedback":
            suggested_value = data.get("suggested_text")
            if not isinstance(suggested_value, str) or not suggested_value.strip():
                return _reject(
                    validation_id,
                    "schema_invalid",
                    path="suggested_text",
                    detail="suggested_text is required for writing_feedback",
                    repairable=True,
                )
            explanation_value = data.get("explanation")
            if not isinstance(explanation_value, str) or not explanation_value.strip():
                return _reject(
                    validation_id,
                    "schema_invalid",
                    path="explanation",
                    detail="explanation is required for writing_feedback",
                    repairable=True,
                )
            examples_value = data.get("examples")
            examples_list: list[str] = []
            if examples_value is not None:
                if not isinstance(examples_value, list):
                    return _reject(
                        validation_id,
                        "schema_invalid",
                        path="examples",
                        detail="examples must be an array of strings",
                        repairable=True,
                    )
                for index, value in enumerate(examples_value):
                    if not isinstance(value, str):
                        return _reject(
                            validation_id,
                            "schema_invalid",
                            path=f"examples[{index}]",
                            detail="example must be text",
                            repairable=True,
                        )
                    examples_list.append(value)
            writing = WritingFeedback(
                suggested_text=suggested_value,
                explanation=explanation_value,
                examples=tuple(examples_list),
            )

        # Citation and abstention failures are non-repairable. Check them before
        # the repairable length and markup rules so a mixed failure stays unsafe.
        published = set(evidence.published_ids)
        withheld = set(evidence.unpublished_ids)
        for source_id in source_ids:
            if source_id in published:
                continue
            if source_id in withheld:
                return _reject(
                    validation_id,
                    "citation_unpublished",
                    path="source_ids",
                    detail="source exists but is not published",
                )
            return _reject(
                validation_id,
                "citation_unknown",
                path="source_ids",
                detail="source is not in the retrieved published evidence",
            )

        known_ids = tuple(
            dict.fromkeys((*evidence.published_ids, *evidence.unpublished_ids))
        )
        source_id_set = set(source_ids)
        for index, tip in enumerate(tips):
            for chunk_id in known_ids:
                if chunk_id in source_id_set:
                    continue
                if not _mentions_chunk_id(tip, chunk_id):
                    continue
                code: ValidationCode = (
                    "citation_unpublished"
                    if chunk_id in withheld
                    else "citation_unknown"
                )
                return _reject(
                    validation_id,
                    code,
                    path=f"tips[{index}]",
                    detail=(
                        "a citation must be declared in source_ids, "
                        "not only in tips"
                    ),
                )
            for chunk_id in known_ids:
                pattern = _chunk_id_family_pattern(chunk_id)
                if pattern is None:
                    continue
                for match in pattern.finditer(tip):
                    if match.group(0) in source_id_set:
                        continue
                    return _reject(
                        validation_id,
                        "citation_unknown",
                        path=f"tips[{index}]",
                        detail=(
                            "a citation must be declared in source_ids, "
                            "not only in tips"
                        ),
                    )

        if len(set(source_ids)) != len(source_ids):
            return _reject(
                validation_id,
                "schema_invalid",
                path="source_ids",
                detail="source_ids must not contain duplicates",
                repairable=True,
            )

        if abstained:
            if source_ids:
                return _reject(
                    validation_id,
                    "abstention_inconsistent",
                    path="source_ids",
                    detail="an abstained response must not cite sources",
                )
            if INSUFFICIENT_EVIDENCE_PHRASE not in answer:
                return _reject(
                    validation_id,
                    "abstention_inconsistent",
                    path="answer",
                    detail="an abstained response must contain the limitation phrase",
                )
        elif task == "lesson_help" and not source_ids:
            return _reject(
                validation_id,
                "abstention_inconsistent",
                path="source_ids",
                detail="lesson_help requires a source unless abstained",
            )

        allowed_fields = set(COMMON_FIELDS)
        if task == "writing_feedback":
            allowed_fields.update(WRITING_FIELDS)
        unknown_fields = sorted(set(data) - allowed_fields)
        if unknown_fields:
            return _reject(
                validation_id,
                "schema_invalid",
                path=unknown_fields[0],
                detail="unknown field",
                repairable=True,
            )

        if len(source_ids) > MAX_SOURCE_IDS:
            return _reject(
                validation_id,
                "over_length",
                path="source_ids",
                detail=f"source_ids exceeds {MAX_SOURCE_IDS} entries",
                repairable=True,
            )
        if len(answer) > MAX_ANSWER_CHARS:
            return _reject(
                validation_id,
                "over_length",
                path="answer",
                detail=f"answer exceeds {MAX_ANSWER_CHARS} characters",
                repairable=True,
            )
        if follow_up is not None and len(follow_up) > MAX_FOLLOW_UP_CHARS:
            return _reject(
                validation_id,
                "over_length",
                path="follow_up",
                detail=f"follow_up exceeds {MAX_FOLLOW_UP_CHARS} characters",
                repairable=True,
            )
        if len(tips) > MAX_TIPS:
            return _reject(
                validation_id,
                "over_length",
                path="tips",
                detail=f"tips exceeds {MAX_TIPS} entries",
                repairable=True,
            )
        for index, tip in enumerate(tips):
            if len(tip) > MAX_TIP_CHARS:
                return _reject(
                    validation_id,
                    "over_length",
                    path=f"tips[{index}]",
                    detail=f"tip exceeds {MAX_TIP_CHARS} characters",
                    repairable=True,
                )
        if writing is not None:
            if len(writing.suggested_text) > MAX_SUGGESTED_TEXT_CHARS:
                return _reject(
                    validation_id,
                    "over_length",
                    path="suggested_text",
                    detail=f"suggested_text exceeds {MAX_SUGGESTED_TEXT_CHARS} characters",
                    repairable=True,
                )
            if len(writing.explanation) > MAX_EXPLANATION_CHARS:
                return _reject(
                    validation_id,
                    "over_length",
                    path="explanation",
                    detail=f"explanation exceeds {MAX_EXPLANATION_CHARS} characters",
                    repairable=True,
                )
            if len(writing.examples) > MAX_EXAMPLES:
                return _reject(
                    validation_id,
                    "over_length",
                    path="examples",
                    detail=f"examples exceeds {MAX_EXAMPLES} entries",
                    repairable=True,
                )
            for index, example in enumerate(writing.examples):
                if len(example) > MAX_EXAMPLE_CHARS:
                    return _reject(
                        validation_id,
                        "over_length",
                        path=f"examples[{index}]",
                        detail=f"example exceeds {MAX_EXAMPLE_CHARS} characters",
                        repairable=True,
                    )

        text_fields: list[tuple[str, str]] = [("answer", answer)]
        if follow_up is not None:
            text_fields.append(("follow_up", follow_up))
        text_fields.extend(
            (f"tips[{index}]", tip) for index, tip in enumerate(tips)
        )
        if writing is not None:
            text_fields.extend(
                (
                    ("suggested_text", writing.suggested_text),
                    ("explanation", writing.explanation),
                )
            )
            text_fields.extend(
                (f"examples[{index}]", example)
                for index, example in enumerate(writing.examples)
            )
        for path, text in text_fields:
            if _has_unsafe_markup(text):
                return _reject(
                    validation_id,
                    "unsafe_markup",
                    path=path,
                    detail="raw HTML, links and URLs are not allowed",
                    repairable=True,
                )

        response = ValidatedResponse(
            task=task,
            abstained=abstained,
            source_ids=source_ids,
            answer=answer,
            validation_id=validation_id,
            follow_up=follow_up,
            tips=tips,
            writing_feedback=writing,
        )
        return ValidationVerdict(
            accepted=True,
            code="accepted",
            validation_id=validation_id,
            validated_text=response.answer,
            response=response,
        )
