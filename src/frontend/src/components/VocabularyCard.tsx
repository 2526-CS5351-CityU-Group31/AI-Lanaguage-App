/**
 * VocabularyCard - displays one published vocabulary entry and state actions.
 *
 * Element: frontend vocabulary display
 * Implements: FR-VOC-001, FR-VOC-002; ADR-008
 *
 * The confirmed (last successful) familiarity state is indicated via
 * aria-pressed and an accessible status message. It is only set after the
 * server accepts the POST; a failed request never changes it.
 */
import type { FamiliarityState, VocabularyCard as VocabCard } from "../api/types";

const STATES: FamiliarityState[] = ["learning", "familiar", "mastered"];

export default function VocabularyCard({
  card,
  onStateChange,
  saving,
  savedState,
}: {
  card: VocabCard;
  onStateChange: (entryId: string, state: FamiliarityState) => void;
  saving?: boolean;
  savedState?: FamiliarityState;
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
        {STATES.map((state) => {
          const isSelected = savedState === state;
          return (
            <button
              key={state}
              type="button"
              disabled={saving}
              aria-pressed={isSelected}
              className={isSelected ? "state-button is-selected" : "state-button"}
              onClick={() => onStateChange(card.entry_id, state)}
            >
              {state}
            </button>
          );
        })}
      </div>
      {savedState ? (
        <p className="vocab-saved" role="status" aria-live="polite">
          Saved as {savedState}.
        </p>
      ) : null}
    </article>
  );
}
