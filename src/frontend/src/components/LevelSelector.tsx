/**
 * LevelSelector - CEFR level picker restricted to A1-B2.
 *
 * Element: frontend form control
 * Implements: FR-PROF-001; INV-CEFR-001
 */
import { CEFR_LEVELS, type CefrLevel } from "../api/types";

export default function LevelSelector({
  value,
  onChange,
  id = "cefr-level",
}: {
  value: CefrLevel;
  onChange: (level: CefrLevel) => void;
  id?: string;
}) {
  return (
    <label htmlFor={id} className="field">
      <span>CEFR level</span>
      <select
        id={id}
        name="cefr_level"
        value={value}
        onChange={(e) => onChange(e.target.value as CefrLevel)}
      >
        {CEFR_LEVELS.map((level) => (
          <option key={level} value={level}>
            {level}
          </option>
        ))}
      </select>
    </label>
  );
}
