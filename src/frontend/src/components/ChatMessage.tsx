/**
 * ChatMessage - renders a single assistant turn plus scope status.
 *
 * Element: frontend chat display
 * Implements: FR-CHAT-001, FR-FEED-001, FR-RAG-001;
 *             INV-SCOPE-002, INV-SCOPE-004, INV-SCOPE-005, INV-CITE-001; ADR-005
 *
 * Scope status is displayed separately from the tutor response. Insufficient
 * evidence is the ADR-005 abstained flag, not a scope status.
 */
import type { ChatTurnResponse } from "../api/types";
import { LEARNER_MODE_TO_TUTOR_TASK, type LearnerMode } from "../api/types";
import SourceCitation from "./SourceCitation";
import WritingFeedback from "./WritingFeedback";

export default function ChatMessage({
  originalText,
  learnerMode,
  response,
}: {
  originalText: string;
  learnerMode: LearnerMode;
  response: ChatTurnResponse;
}) {
  const tutorTask =
    response.task ??
    (learnerMode === "vocabulary_question"
      ? undefined
      : LEARNER_MODE_TO_TUTOR_TASK[learnerMode]);

  const isWriting = tutorTask === "writing_feedback";
  const hasScope = Boolean(response.scope_status);

  return (
    <article className="chat-turn" aria-label="Tutor response">
      {!isWriting ? <p className="user-bubble"><span className="sr-only">You: </span>{originalText}</p> : null}
      <div className="chat-message tutor-bubble">
        <p className="message-author">English Companion</p>
        {hasScope ? (
          <div role="status" aria-label="Scope status" className="scope-status">
            <span className="scope-label">Scope:</span> {response.scope_status}
            {response.scope_message ? <p className="scope-message">{response.scope_message}</p> : null}
          </div>
        ) : null}

        {isWriting ? (
          <WritingFeedback
            original={originalText}
            answer={response.answer}
            suggestedText={response.suggested_text}
            explanation={response.explanation}
            examples={response.examples}
          />
        ) : (
          <>
            {response.answer ? <p className="answer">{response.answer}</p> : null}
            {response.follow_up ? <p className="follow-up">{response.follow_up}</p> : null}
            {response.abstained ? (
              <p className="abstention">
                The approved lessons do not have enough evidence to answer that question.
              </p>
            ) : response.source_ids ? (
              <SourceCitation sourceIds={response.source_ids} sources={response.sources} />
            ) : null}
          </>
        )}
      </div>
    </article>
  );
}
