/**
 * LoadingState - accessible loading indicator.
 *
 * Element: shared UI state
 * Implements: FR-CHAT-001, FR-DASH-001; VS-16
 */
export default function LoadingState({ label = "Loading…" }: { label?: string }) {
  return (
    <div role="status" aria-live="polite" className="state state-loading">
      <span className="spinner" aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}
