/**
 * ErrorState - accessible error panel with optional retry.
 *
 * Element: shared UI state
 * Implements: FR-CHAT-001, FR-DASH-001, FR-VOC-001; VS-16
 */
export default function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div role="alert" className="state state-error">
      <p>{message}</p>
      {onRetry ? (
        <button type="button" onClick={onRetry}>
          Try again
        </button>
      ) : null}
    </div>
  );
}
