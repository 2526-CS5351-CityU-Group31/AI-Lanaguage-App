/**
 * ChatPage - conversational practice with learner mode selection.
 *
 * Element: frontend chat page
 * Implements: FR-CHAT-001, FR-FEED-001, FR-RAG-001;
 *             INV-SCOPE-002, INV-SCOPE-004, INV-SCOPE-005, INV-CITE-001; ADR-005
 *
 * Sends the selected learner_mode to the server; renders the returned tutor
 * response and scope status verbatim. No scope, citation or task value is
 * computed or overridden in the UI.
 */
import { useRef, useState, type FormEvent } from "react";
import { createSession, newRequestId, sendMessage } from "../api/chat";
import { ApiError } from "../api/client";
import type { ChatTurnResponse, LearnerMode } from "../api/types";
import ModeSelector from "../components/ModeSelector";
import ChatMessage from "../components/ChatMessage";
import ErrorState from "../components/ErrorState";
import AppIcon, { type AppIconName } from "../components/AppIcon";

interface Turn {
  originalText: string;
  learnerMode: LearnerMode;
  response: ChatTurnResponse;
}

const MODE_EMPTY_STATE: Record<LearnerMode, { title: string; description: string; icon: AppIconName }> = {
  conversation_practice: { title: "Start a conversation", description: "Choose a starter or write your own message to practise natural English.", icon: "conversation" },
  writing_feedback: { title: "Improve your writing", description: "Paste a sentence or short paragraph to receive structured feedback.", icon: "writing" },
  grammar_question: { title: "Ask a grammar question", description: "Describe the rule or sentence that you would like help understanding.", icon: "grammar" },
  vocabulary_question: { title: "Explore new vocabulary", description: "Ask about a word, phrase, meaning or example sentence.", icon: "vocabulary" },
  lesson_question: { title: "Review a lesson", description: "Ask a question grounded in the approved English lesson materials.", icon: "lesson" },
};

const STARTERS: Record<LearnerMode, string[]> = {
  conversation_practice: ["Help me introduce myself.", "Let's talk about travelling.", "Practise a job interview with me."],
  writing_feedback: ["Please review this email: ", "Help me improve this paragraph: "],
  grammar_question: ["When should I use the present perfect?", "Explain articles: a, an and the."],
  vocabulary_question: ["What does resilient mean?", "Teach me useful words for travelling."],
  lesson_question: ["Explain the main point of this lesson.", "Can you give me an example from the lesson?"],
};

export default function ChatPage() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [mode, setMode] = useState<LearnerMode>("conversation_practice");
  const [input, setInput] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const sendingRef = useRef(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  async function ensureSession(): Promise<string> {
    if (sessionId) return sessionId;
    const { session_id } = await createSession();
    setSessionId(session_id);
    return session_id;
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const text = input.trim();
    if (!text || sendingRef.current) return;

    sendingRef.current = true;
    setSending(true);
    setError(null);
    try {
      const id = await ensureSession();
      const response = await sendMessage(id, {
        learner_mode: mode,
        message: text,
        request_id: newRequestId(),
      });
      setTurns((prev) => [...prev, { originalText: text, learnerMode: mode, response }]);
      setInput("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to send message.");
    } finally {
      sendingRef.current = false;
      setSending(false);
    }
  }

  function chooseStarter(starter: string) {
    setInput(starter);
    textareaRef.current?.focus();
  }

  const emptyState = MODE_EMPTY_STATE[mode];

  return (
    <main className="page chat-page">
      <header className="page-header">
        <h1>Practice</h1>
        <p>Choose a learning mode and practise English with your AI tutor.</p>
      </header>
      <ModeSelector value={mode} onChange={setMode} />

      <div className="practice-workspace">
        <section className="conversation" aria-label="Conversation" aria-live="polite">
          {turns.length === 0 ? (
            <div className="conversation-empty">
              <span className="empty-icon"><AppIcon name={emptyState.icon} /></span>
              <h2>{emptyState.title}</h2>
              <p>{emptyState.description}</p>
              <div className="starter-list" role="group" aria-label="Conversation starters">
                {STARTERS[mode].map((starter) => (
                  <button key={starter} type="button" className="starter-chip" onClick={() => chooseStarter(starter)}>
                    {starter.trim()}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="turn-list">
              {turns.map((turn, i) => (
                <ChatMessage
                  key={i}
                  originalText={turn.originalText}
                  learnerMode={turn.learnerMode}
                  response={turn.response}
                />
              ))}
            </div>
          )}
        </section>

        {error ? <ErrorState message={error} /> : null}

        <form onSubmit={handleSubmit} className="composer" aria-label="Composer">
          <label htmlFor="message" className="sr-only">Message</label>
          <textarea
            ref={textareaRef}
            id="message"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            rows={2}
            placeholder="Write your message in English…"
          />
          <div className="composer-footer">
            <span className="composer-hint">Your selected practice mode will guide the response.</span>
            <button className="send-button" type="submit" disabled={sending || input.trim().length === 0}>
              <span>{sending ? "Sending…" : "Send"}</span>
              <AppIcon name="send" />
            </button>
          </div>
        </form>
      </div>
    </main>
  );
}
