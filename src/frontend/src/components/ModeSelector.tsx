/**
 * ModeSelector - learner practice mode picker (radio group).
 *
 * Element: frontend form control
 * Implements: FR-CHAT-001; ADR-005 (learner mode separate from tutor task)
 */
import type { LearnerMode } from "../api/types";
import AppIcon, { type AppIconName } from "./AppIcon";

const MODES: Array<{
  value: LearnerMode;
  label: string;
  description: string;
  icon: AppIconName;
}> = [
  { value: "conversation_practice", label: "Conversation practice", description: "Build fluency through guided dialogue.", icon: "conversation" },
  { value: "writing_feedback", label: "Writing feedback", description: "Improve clarity, grammar and structure.", icon: "writing" },
  { value: "grammar_question", label: "Grammar question", description: "Understand rules with clear examples.", icon: "grammar" },
  { value: "vocabulary_question", label: "Vocabulary question", description: "Learn meanings, usage and context.", icon: "vocabulary" },
  { value: "lesson_question", label: "Lesson question", description: "Ask about the approved lesson materials.", icon: "lesson" },
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
      <div className="mode-grid">
        {MODES.map((mode) => (
          <label key={mode.value} className="mode-card">
            <input
              className="mode-radio"
              type="radio"
              name="learner_mode"
              value={mode.value}
              checked={value === mode.value}
              onChange={() => onChange(mode.value)}
            />
            <span className="mode-icon"><AppIcon name={mode.icon} /></span>
            <span className="mode-copy">
              <span className="mode-label">{mode.label}</span>
              <span className="mode-description">{mode.description}</span>
            </span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}
