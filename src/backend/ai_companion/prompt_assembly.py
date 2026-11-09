"""PromptAssembler - layered context assembly within a fixed prompt-token budget.

Element: PromptAssembler
Implements: ADR-006 §Decision and §Assembly pipeline; NFR-COST-001, FR-CHAT-001.
Structural support only for NFR-SEC-001: retrieved evidence is delimited as
untrusted data. The authoritative injection gate remains outside this module.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from enum import Enum
from typing import Callable, Literal, Mapping, Sequence

TokenCounter = Callable[[str], int]
HistoryRole = Literal["learner", "tutor"]

DEFAULT_TOKEN_BUDGET = 1500
DEFAULT_COMPACTION_MESSAGE_LIMIT = 6
NEAR_DUPLICATE_RATIO = 0.9
EVIDENCE_START = "<<<UNTRUSTED_EVIDENCE>>>"
EVIDENCE_END = "<<<END_UNTRUSTED_EVIDENCE>>>"
ESCAPED_DELIMITER = "[escaped_delimiter]"


class LayerName(str, Enum):
    """ADR-006 §Context layers: the canonical assembly layer names."""

    IDENTITY_POLICY = "identity_policy"
    STANDING_CONSTRAINTS = "standing_constraints"
    RESPONSE_SCHEMA = "response_schema"
    LEARNER_PROFILE = "learner_profile"
    RESUMABLE_STATE = "resumable_state"
    CONSTRAINT_REINJECTION = "constraint_reinjection"
    RETRIEVED_EVIDENCE = "retrieved_evidence"
    RECENT_HISTORY = "recent_history"
    CURRENT_TURN = "current_turn"


class AssemblyErrorCode(str, Enum):
    """ADR-006 / RP-017: typed error states returned to the caller."""

    INVALID_CONFIG = "invalid_config"
    INVALID_REQUEST = "invalid_request"
    CURRENT_TURN_TOO_LONG = "current_turn_too_long"
    PROTECTED_LAYER_OVER_BUDGET = "protected_layer_over_budget"
    BUDGET_UNSATISFIABLE = "budget_unsatisfiable"


@dataclass(frozen=True)
class EvidenceChunk:
    """ADR-006: one retrieved chunk; its text is untrusted data."""

    chunk_id: str
    title: str
    section: str
    text: str


@dataclass(frozen=True)
class HistoryTurn:
    """ADR-006: one role-labelled conversation turn."""

    role: HistoryRole
    content: str


@dataclass(frozen=True)
class PromptAssemblyRequest:
    """ADR-006 §Context layers: all caller-supplied assembly inputs."""

    prompt_version: str
    identity_policy: str
    standing_constraints: str
    response_schema: str
    learner_profile: str
    resumable_state: str
    evidence: tuple[EvidenceChunk, ...]
    history: tuple[HistoryTurn, ...]
    current_turn: str


@dataclass(frozen=True)
class LayerBudget:
    """ADR-006 §Context layers: the default per-layer token caps."""

    identity_policy: int = 200
    standing_constraints: int = 150
    response_schema: int = 150
    learner_profile: int = 100
    resumable_state: int = 100
    retrieved_evidence: int = 400
    recent_history: int = 300
    current_turn: int = 100

    def __post_init__(self) -> None:
        for name, value in self.as_mapping().items():
            if value <= 0:
                raise ValueError(f"layer budget for {name.value} must be positive")

    def as_mapping(self) -> Mapping[LayerName, int]:
        """ADR-006: expose the caps keyed by canonical layer name."""
        return {
            LayerName.IDENTITY_POLICY: self.identity_policy,
            LayerName.STANDING_CONSTRAINTS: self.standing_constraints,
            LayerName.RESPONSE_SCHEMA: self.response_schema,
            LayerName.LEARNER_PROFILE: self.learner_profile,
            LayerName.RESUMABLE_STATE: self.resumable_state,
            LayerName.RETRIEVED_EVIDENCE: self.retrieved_evidence,
            LayerName.RECENT_HISTORY: self.recent_history,
            LayerName.CURRENT_TURN: self.current_turn,
        }

    @property
    def total(self) -> int:
        """NFR-COST-001: the caps must sum to the prompt-token ceiling."""
        return sum(self.as_mapping().values())


@dataclass(frozen=True)
class AssemblyConfig:
    """NFR-COST-001 / ADR-006: frozen assembly configuration."""

    token_budget: int = DEFAULT_TOKEN_BUDGET
    compaction_message_limit: int = DEFAULT_COMPACTION_MESSAGE_LIMIT
    layer_budgets: LayerBudget = field(default_factory=LayerBudget)

    def __post_init__(self) -> None:
        if self.token_budget <= 0:
            raise ValueError("token_budget must be positive")
        if self.layer_budgets.total != self.token_budget:
            raise ValueError("layer budgets must sum to token_budget")
        if not 4 <= self.compaction_message_limit <= 20:
            raise ValueError("compaction_message_limit must be between 4 and 20")


@dataclass(frozen=True)
class LayerSlice:
    """ADR-006: one rendered prompt layer and its budget outcome."""

    name: LayerName
    text: str
    token_count: int
    truncated: bool = False
    re_injected: bool = False


@dataclass(frozen=True)
class AssemblyMetadata:
    """ADR-006 §Assembly pipeline step 6: audit-facing assembly metadata."""

    estimated_prompt_tokens: int
    layer_tokens: tuple[tuple[LayerName, int], ...]
    compaction_applied: bool
    compacted_history_count: int
    dropped_chunk_ids: tuple[str, ...]
    dropped_history_count: int
    prompt_version: str
    budget: int


@dataclass(frozen=True)
class AssemblyResult:
    """ADR-006: the assembled prompt and its reproducible metadata."""

    prompt: str
    layers: tuple[LayerSlice, ...]
    metadata: AssemblyMetadata

    @property
    def token_count(self) -> int:
        """NFR-COST-001: estimated tokens in the final assembled prompt."""
        return self.metadata.estimated_prompt_tokens


class PromptAssemblyError(Exception):
    """ADR-006 / RP-017: typed assembly failure; the caller maps it before a model call."""

    code: AssemblyErrorCode
    message: str
    layer: LayerName | None

    def __init__(
        self,
        code: AssemblyErrorCode,
        message: str,
        *,
        layer: LayerName | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.layer = layer


def estimate_tokens(text: str) -> int:
    """NFR-COST-001 / ADR-006: deterministic fallback token estimate."""
    return math.ceil(len(text) / 4)


def _render_text_layer(name: LayerName, content: str) -> str:
    return f"[{name.value}]\n{content}\n"


def _truncate_to_fit(
    content: str,
    cap: int,
    counter: TokenCounter,
    render: Callable[[str], str],
) -> tuple[str, bool]:
    if counter(render(content)) <= cap:
        return content, False
    low = 0
    high = len(content)
    while low < high:
        middle = (low + high + 1) // 2
        if counter(render(content[:middle])) <= cap:
            low = middle
        else:
            high = middle - 1
    return content[:low], True


def _normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return re.sub(r"\s+", " ", normalized).strip()


def _dedupe_evidence(
    chunks: Sequence[EvidenceChunk],
) -> tuple[tuple[EvidenceChunk, ...], tuple[str, ...]]:
    """ADR-006 §Assembly pipeline step 1: dedupe by chunk_id and near-duplicate text."""
    seen_ids: set[str] = set()
    kept: list[EvidenceChunk] = []
    kept_text: list[str] = []
    dropped: list[str] = []

    for chunk in chunks:
        if chunk.chunk_id in seen_ids:
            dropped.append(chunk.chunk_id)
            continue
        normalized = _normalize_text(chunk.text)
        if any(
            SequenceMatcher(None, normalized, existing).ratio() >= NEAR_DUPLICATE_RATIO
            for existing in kept_text
        ):
            dropped.append(chunk.chunk_id)
            continue
        seen_ids.add(chunk.chunk_id)
        kept.append(chunk)
        kept_text.append(normalized)

    return tuple(kept), tuple(dropped)


def _single_line(text: str) -> str:
    return re.sub(r"[\r\n]+", " ", text)


def _escape_evidence_delimiters(text: str) -> str:
    return text.replace(EVIDENCE_END, ESCAPED_DELIMITER).replace(
        EVIDENCE_START, ESCAPED_DELIMITER
    )


def _format_chunk(chunk: EvidenceChunk) -> str:
    return (
        f"chunk_id: {_single_line(chunk.chunk_id)}\n"
        f"title: {_single_line(chunk.title)}\n"
        f"section: {_single_line(chunk.section)}\n"
        f"text: {_escape_evidence_delimiters(chunk.text)}"
    )


def _evidence_text(chunks: Sequence[EvidenceChunk]) -> str:
    body = "\n\n".join(_format_chunk(chunk) for chunk in chunks)
    header = f"[{LayerName.RETRIEVED_EVIDENCE.value}]\n{EVIDENCE_START}\n"
    footer = f"\n{EVIDENCE_END}\n"
    return f"{header}{body}{footer}"


def _fit_single_evidence_chunk(
    chunk: EvidenceChunk,
    cap: int,
    counter: TokenCounter,
) -> EvidenceChunk | None:
    def render(text: str) -> str:
        candidate = EvidenceChunk(
            chunk_id=chunk.chunk_id,
            title=chunk.title,
            section=chunk.section,
            text=text,
        )
        return _evidence_text((candidate,))

    if counter(render("")) > cap:
        return None
    if counter(render(chunk.text)) <= cap:
        return chunk

    low = 0
    high = len(chunk.text)
    while low < high:
        middle = (low + high + 1) // 2
        if counter(render(chunk.text[:middle])) <= cap:
            low = middle
        else:
            high = middle - 1

    return EvidenceChunk(
        chunk_id=chunk.chunk_id,
        title=chunk.title,
        section=chunk.section,
        text=chunk.text[:low],
    )


def _select_evidence(
    chunks: Sequence[EvidenceChunk],
    cap: int,
    counter: TokenCounter,
) -> tuple[list[EvidenceChunk], list[str], bool]:
    """ADR-006 §Assembly pipeline step 3: keep ranked evidence within the cap."""
    if not chunks:
        return [], [], False

    included: list[EvidenceChunk] = []
    dropped: list[str] = []
    truncated = False

    for index, chunk in enumerate(chunks):
        if counter(_evidence_text((*included, chunk))) <= cap:
            included.append(chunk)
            continue

        if not included:
            fitted = _fit_single_evidence_chunk(chunk, cap, counter)
            if fitted is None:
                dropped.extend(item.chunk_id for item in chunks[index:])
                return [], dropped, False
            included.append(fitted)
            truncated = True
            dropped.extend(item.chunk_id for item in chunks[index + 1 :])
        else:
            dropped.extend(item.chunk_id for item in chunks[index:])
        break

    return included, dropped, truncated


def _history_text(turns: Sequence[HistoryTurn], marker: str) -> str:
    parts = [f"[{LayerName.RECENT_HISTORY.value}]\n"]
    if marker:
        parts.append(marker)
    for turn in turns:
        parts.append(f"{turn.role}: {turn.content}\n")
    return "".join(parts)


def _select_history(
    turns: Sequence[HistoryTurn],
    marker: str,
    cap: int,
    counter: TokenCounter,
) -> tuple[list[HistoryTurn], str, list[HistoryTurn], bool]:
    """ADR-006: keep the newest history within the cap, then truncate if needed."""
    remaining = list(turns)
    dropped: list[HistoryTurn] = []
    truncated = False

    while remaining and counter(_history_text(remaining, marker)) > cap:
        dropped.append(remaining.pop(0))

    if not remaining and marker and counter(_history_text((), marker)) > cap:
        marker = ""

    if remaining and counter(_history_text(remaining, marker)) > cap:
        newest = remaining[-1]

        def render(text: str) -> str:
            candidate = (*remaining[:-1], HistoryTurn(newest.role, text))
            return _history_text(candidate, marker)

        if counter(render("")) > cap:
            dropped.extend(remaining)
            remaining = []
            if marker and counter(_history_text((), marker)) > cap:
                marker = ""
        else:
            fitted, truncated = _truncate_to_fit(newest.content, cap, counter, render)
            remaining[-1] = HistoryTurn(newest.role, fitted)

    return remaining, marker, dropped, truncated


def _prepare_history(
    history: Sequence[HistoryTurn],
    limit: int,
) -> tuple[list[HistoryTurn], str, bool, int]:
    """ADR-006: compact all but the last six messages with a deterministic marker."""
    if len(history) > limit:
        older_count = len(history) - limit
        marker = f"[compacted {older_count} earlier messages]\n"
        return list(history[-limit:]), marker, True, older_count
    return list(history), "", False, 0


class PromptAssembler:
    """ADR-006: advisory assembler; it builds model input but never calls a model."""

    def __init__(
        self,
        config: AssemblyConfig | None = None,
        token_counter: TokenCounter | None = None,
    ) -> None:
        self._config = config if config is not None else AssemblyConfig()
        self._counter: TokenCounter = (
            token_counter if token_counter is not None else estimate_tokens
        )

    @property
    def config(self) -> AssemblyConfig:
        """ADR-006: the frozen configuration used by this assembler."""
        return self._config

    def assemble(self, request: PromptAssemblyRequest) -> AssemblyResult:
        """Assemble one prompt within the configured budget.

        Implements: ADR-006 §Assembly pipeline; NFR-COST-001, FR-CHAT-001.
        Raises a typed PromptAssemblyError before returning any partial prompt.
        """
        self._validate_request(request)
        budgets = self._config.layer_budgets.as_mapping()

        identity = self._protected_layer(
            LayerName.IDENTITY_POLICY,
            request.identity_policy,
            budgets[LayerName.IDENTITY_POLICY],
        )
        constraints = self._protected_layer(
            LayerName.STANDING_CONSTRAINTS,
            request.standing_constraints,
            budgets[LayerName.STANDING_CONSTRAINTS],
        )
        schema = self._protected_layer(
            LayerName.RESPONSE_SCHEMA,
            request.response_schema,
            budgets[LayerName.RESPONSE_SCHEMA],
        )
        current = self._current_turn_layer(
            request.current_turn, budgets[LayerName.CURRENT_TURN]
        )

        profile = self._cuttable_text_layer(
            LayerName.LEARNER_PROFILE,
            request.learner_profile,
            budgets[LayerName.LEARNER_PROFILE],
        )
        state = self._cuttable_text_layer(
            LayerName.RESUMABLE_STATE,
            request.resumable_state,
            budgets[LayerName.RESUMABLE_STATE],
        )

        reinjection_text = _render_text_layer(
            LayerName.CONSTRAINT_REINJECTION, request.standing_constraints
        )
        reinjection = LayerSlice(
            name=LayerName.CONSTRAINT_REINJECTION,
            text=reinjection_text,
            token_count=self._counter(reinjection_text),
            re_injected=True,
        )

        deduped, dedupe_dropped = _dedupe_evidence(request.evidence)
        evidence_included, evidence_dropped, evidence_truncated = _select_evidence(
            deduped,
            budgets[LayerName.RETRIEVED_EVIDENCE],
            self._counter,
        )
        dropped_chunks = [*dedupe_dropped, *evidence_dropped]

        retained, marker, count_compaction, compacted_count = _prepare_history(
            request.history, self._config.compaction_message_limit
        )
        retained, marker, history_dropped, history_truncated = _select_history(
            retained,
            marker,
            budgets[LayerName.RECENT_HISTORY],
            self._counter,
        )
        dropped_history = list(history_dropped)
        compaction_applied = count_compaction or bool(history_dropped)

        while True:
            evidence_layer: LayerSlice | None = None
            if evidence_included:
                evidence_text = _evidence_text(evidence_included)
                evidence_layer = LayerSlice(
                    name=LayerName.RETRIEVED_EVIDENCE,
                    text=evidence_text,
                    token_count=self._counter(evidence_text),
                    truncated=evidence_truncated,
                )

            history_layer: LayerSlice | None = None
            if retained or marker:
                history_text = _history_text(retained, marker)
                history_layer = LayerSlice(
                    name=LayerName.RECENT_HISTORY,
                    text=history_text,
                    token_count=self._counter(history_text),
                    truncated=history_truncated,
                )

            layers: list[LayerSlice] = [identity, constraints, schema]
            if profile is not None:
                layers.append(profile)
            if state is not None:
                layers.append(state)
            layers.append(reinjection)
            if evidence_layer is not None:
                layers.append(evidence_layer)
            if history_layer is not None:
                layers.append(history_layer)
            layers.append(current)

            prompt = "".join(layer.text for layer in layers)
            total_tokens = self._counter(prompt)
            if total_tokens <= self._config.token_budget:
                break

            if retained:
                dropped_history.append(retained.pop(0))
                history_truncated = True
                compaction_applied = True
                continue
            if marker:
                marker = ""
                compaction_applied = True
                continue
            if evidence_included:
                dropped_chunks.append(evidence_included.pop().chunk_id)
                evidence_truncated = True
                continue
            if state is not None:
                state = None
                continue
            if profile is not None:
                profile = None
                continue
            raise PromptAssemblyError(
                AssemblyErrorCode.BUDGET_UNSATISFIABLE,
                "protected layers and constraint re-injection exceed the prompt budget",
            )

        metadata = AssemblyMetadata(
            estimated_prompt_tokens=total_tokens,
            layer_tokens=tuple((layer.name, layer.token_count) for layer in layers),
            compaction_applied=compaction_applied,
            compacted_history_count=compacted_count,
            dropped_chunk_ids=tuple(dropped_chunks),
            dropped_history_count=len(dropped_history),
            prompt_version=request.prompt_version,
            budget=self._config.token_budget,
        )
        return AssemblyResult(
            prompt=prompt,
            layers=tuple(layers),
            metadata=metadata,
        )

    def _validate_request(self, request: PromptAssemblyRequest) -> None:
        required = (
            request.prompt_version,
            request.identity_policy,
            request.standing_constraints,
            request.response_schema,
            request.current_turn,
        )
        if any(not value.strip() for value in required):
            raise PromptAssemblyError(
                AssemblyErrorCode.INVALID_REQUEST,
                "protected text fields and the current turn must be non-empty",
            )
        for chunk in request.evidence:
            if not chunk.chunk_id.strip():
                raise PromptAssemblyError(
                    AssemblyErrorCode.INVALID_REQUEST,
                    "evidence chunk_id must be non-empty",
                )
        for turn in request.history:
            if turn.role not in ("learner", "tutor"):
                raise PromptAssemblyError(
                    AssemblyErrorCode.INVALID_REQUEST,
                    "history role must be learner or tutor",
                )

    def _protected_layer(
        self,
        name: LayerName,
        content: str,
        cap: int,
    ) -> LayerSlice:
        text = _render_text_layer(name, content)
        if self._counter(text) > cap:
            raise PromptAssemblyError(
                AssemblyErrorCode.PROTECTED_LAYER_OVER_BUDGET,
                f"{name.value} exceeds its {cap}-token cap",
                layer=name,
            )
        return LayerSlice(name=name, text=text, token_count=self._counter(text))

    def _current_turn_layer(self, content: str, cap: int) -> LayerSlice:
        text = _render_text_layer(LayerName.CURRENT_TURN, content)
        if self._counter(text) > cap:
            raise PromptAssemblyError(
                AssemblyErrorCode.CURRENT_TURN_TOO_LONG,
                f"current turn exceeds its {cap}-token cap",
                layer=LayerName.CURRENT_TURN,
            )
        return LayerSlice(
            name=LayerName.CURRENT_TURN,
            text=text,
            token_count=self._counter(text),
        )

    def _cuttable_text_layer(
        self,
        name: LayerName,
        content: str,
        cap: int,
    ) -> LayerSlice | None:
        if not content:
            return None
        text, truncated = _truncate_to_fit(
            content,
            cap,
            self._counter,
            lambda value: _render_text_layer(name, value),
        )
        rendered = _render_text_layer(name, text)
        if self._counter(rendered) > cap:
            return None
        return LayerSlice(
            name=name,
            text=rendered,
            token_count=self._counter(rendered),
            truncated=truncated,
        )
