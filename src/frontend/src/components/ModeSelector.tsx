/**
 * ModeSelector - learner practice mode picker (radio group).
 *
 * Element: frontend form control
 * Implements: FR-CHAT-001; ADR-005 (learner mode separate from tutor task)
 */
import type { LearnerMode } from "../api/types";

const MODES: { value: LearnerMode; label: string }[] = [
  { value: "conversation_practice", label: "Conversation practice" },
  { value: "writing_feedback", label: "Writing feedback" },
  { value: "grammar_question", label: "Grammar question" },
  { value: "vocabulary_question", label: "Vocabulary question" },
  { value: "lesson_question", label: "Lesson question" },
];

export default function ModeSelector({
  value,
  onChange,
}: {
  value: LearnerMode;
  onChange: (mode: LearnerMode) => void;
}) {
  return (
    <fieldset className="mode-selector">
      <legend>Practice mode</legend>
      {MODES.map((mode) => (
        <label key={mode.value} className="radio">
          <input
            type="radio"
            name="learner_mode"
            value={mode.value}
            checked={value === mode.value}
            onChange={() => onChange(mode.value)}
          />
          <span>{mode.label}</span>
        </label>
      ))}
    </fieldset>
  );
}
