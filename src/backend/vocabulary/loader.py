"""VocabularyLoader - seeded random selection of published vocabulary cards.

Element: VocabularyLoader
Implements: FR-VOC-001; ADR-008 (no model call for deterministic selection)
Serves only pre-reviewed, published entries from the verified JSON dataset
matching the learner's CEFR level and topic. Identical seed + inputs yield
identical entries. Read-only: never mutates the dataset.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class VocabularyEntry:
    """A single published vocabulary card.

    Implements: FR-VOC-001
    """

    entry_id: str
    word: str
    sense: str
    level: str
    topic: str
    definition: str
    example: str
    review_status: str = "published"


class VocabularyLoader:
    """Loads the JSON dataset and selects published entries deterministically.

    Implements: FR-VOC-001 (published-only, seeded selection)
    """

    def __init__(self, entries: list[VocabularyEntry]) -> None:
        self._entries = list(entries)

    @classmethod
    def from_json(cls, path: str | Path) -> "VocabularyLoader":
        """Build a loader from the verified JSON dataset file.

        Implements: FR-VOC-001 (verified JSON dataset; read-only)
        """
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data = data.get("entries", [])
        entries = [
            VocabularyEntry(
                entry_id=str(item["entry_id"]),
                word=item["word"],
                sense=item.get("sense", ""),
                level=item["level"],
                topic=item.get("topic", ""),
                definition=item["definition"],
                example=item.get("example", ""),
                review_status=item.get("review_status", "published"),
            )
            for item in data
        ]
        return cls(entries)

    def _eligible(self, level: str, topic: str | None) -> list[VocabularyEntry]:
        """Filter to published entries matching level (and topic if given).

        Implements: FR-VOC-001 (published_only; level/topic match)
        """
        result = [
            entry
            for entry in self._entries
            if entry.review_status == "published" and entry.level == level
        ]
        if topic:
            result = [entry for entry in result if entry.topic == topic]
        return result

    def select_random(
        self,
        *,
        level: str,
        count: int,
        seed: int,
        topic: str | None = None,
    ) -> list[VocabularyEntry]:
        """Return ``count`` published entries; identical seed -> identical result.

        Implements: FR-VOC-001 (identical seed yields identical entries)
        """
        if count < 0:
            raise ValueError("count must be non-negative")
        pool = self._eligible(level=level, topic=topic)
        if count >= len(pool):
            return sorted(pool, key=lambda entry: entry.entry_id)
        rng = random.Random(seed)
        return rng.sample(pool, count)
