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

interface Turn {
  originalText: string;
  learnerMode: LearnerMode;
  response: ChatTurnResponse;
}

export default function ChatPage() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [mode, setMode] = useState<LearnerMode>("conversation_practice");
  const [input, setInput] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const sendingRef = useRef(false);

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

  return (
    <main className="page chat-page">
      <h1>Practice</h1>
      <ModeSelector value={mode} onChange={setMode} />

      <section className="conversation" aria-label="Conversation">
        {turns.length === 0 ? (
          <p className="hint">Choose a mode and start writing in English.</p>
        ) : (
          turns.map((turn, i) => (
            <ChatMessage
              key={i}
              originalText={turn.originalText}
              learnerMode={turn.learnerMode}
              response={turn.response}
            />
          ))
        )}
      </section>

      {error ? <ErrorState message={error} /> : null}

      <form onSubmit={handleSubmit} className="composer" aria-label="Composer">
        <label htmlFor="message" className="field">
          <span>Message</span>
          <textarea
            id="message"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            rows={3}
          />
        </label>
        <button type="submit" disabled={sending || input.trim().length === 0}>
          {sending ? "Sending…" : "Send"}
        </button>
      </form>
    </main>
  );
}
