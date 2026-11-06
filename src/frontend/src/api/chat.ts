/**
 * Chat API adapter.
 *
 * Element: frontend chat client
 * Implements: FR-CHAT-001, FR-FEED-001, FR-RAG-001; INV-CITE-001; ADR-005
 *
 * Provisional request fields (unconfirmed): learner_mode, message, topic,
 * request_id. All response fields are rendered verbatim; no citation or scope
 * value is computed client-side.
 */
import { apiRequest } from "./client";
import type { ChatTurnResponse, SendMessageRequest } from "./types";

export function createSession(): Promise<{ session_id: string }> {
  return apiRequest<{ session_id: string }>("/sessions", { method: "POST" });
}

export function sendMessage(
  sessionId: string,
  payload: SendMessageRequest,
): Promise<ChatTurnResponse> {
  return apiRequest<ChatTurnResponse>(`/sessions/${sessionId}/messages`, {
    method: "POST",
    body: payload,
  });
}

let requestCounter = 0;
export function newRequestId(): string {
  requestCounter += 1;
  return `req_${Date.now()}_${requestCounter}`;
}
