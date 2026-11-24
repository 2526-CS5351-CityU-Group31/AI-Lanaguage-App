/**
 * EmptyState - accessible empty-result panel.
 *
 * Element: shared UI state
 * Implements: FR-VOC-001, FR-DASH-001; VS-16
 */
export default function EmptyState({ message }: { message: string }) {
  return (
    <div role="status" className="state state-empty">
      <p>{message}</p>
    </div>
  );
}
