/**
 * VocabularyCard - displays one published vocabulary entry and state actions.
 *
 * Element: frontend vocabulary display
 * Implements: FR-VOC-001, FR-VOC-002; ADR-008
 */
import type { FamiliarityState, VocabularyCard as VocabCard } from "../api/types";

const STATES: FamiliarityState[] = ["learning", "familiar", "mastered"];

export default function VocabularyCard({
  card,
  onStateChange,
  saving,
}: {
  card: VocabCard;
  onStateChange: (entryId: string, state: FamiliarityState) => void;
  saving?: boolean;
}) {
  return (
    <article className="vocab-card" aria-label={`Vocabulary: ${card.word}`}>
      <h2>{card.word}</h2>
      {card.sense ? <p className="sense">{card.sense}</p> : null}
      <p className="definition">{card.definition}</p>
      <p className="example">{card.example}</p>
      <p className="meta">
        Level {card.level} · {card.topic}
      </p>
      <div className="vocab-actions" role="group" aria-label="Familiarity">
        {STATES.map((state) => (
          <button
            key={state}
            type="button"
            disabled={saving}
            onClick={() => onStateChange(card.entry_id, state)}
          >
            {state}
          </button>
        ))}
      </div>
    </article>
  );
}
