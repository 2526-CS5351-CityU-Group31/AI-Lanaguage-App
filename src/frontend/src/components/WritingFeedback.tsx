/**
 * WritingFeedback - presents original-preserving feedback and a proposal.
 *
 * Element: frontend writing feedback display
 * Implements: FR-FEED-001
 *
 * The original learner text is displayed untouched; suggested_text is shown
 * clearly labelled as a proposal, never replacing the original.
 */
export default function WritingFeedback({
  original,
  answer,
  suggestedText,
  explanation,
  examples,
}: {
  original: string;
  answer?: string;
  suggestedText?: string;
  explanation?: string;
  examples?: string[];
}) {
  return (
    <div className="writing-feedback">
      <section aria-label="Your original text">
        <h2>Your text</h2>
        <p className="original">{original}</p>
      </section>
      {answer ? (
        <section aria-label="Feedback summary">
          <h2>Feedback</h2>
          <p>{answer}</p>
        </section>
      ) : null}
      {suggestedText ? (
        <section aria-label="Suggested revision">
          <h2>Suggested revision (proposal)</h2>
          <p className="suggested">{suggestedText}</p>
        </section>
      ) : null}
      {explanation ? (
        <section aria-label="Explanation">
          <h2>Explanation</h2>
          <p>{explanation}</p>
        </section>
      ) : null}
      {examples && examples.length > 0 ? (
        <section aria-label="Examples">
          <h2>Examples</h2>
          <ul>
            {examples.map((ex, i) => (
              <li key={i}>{ex}</li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
