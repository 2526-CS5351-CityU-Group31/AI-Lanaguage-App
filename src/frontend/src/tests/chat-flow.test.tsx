/**
 * Chat + writing feedback + citations flow tests (test-only).
 *
 * Requirement coverage: FR-CHAT-001, FR-FEED-001, FR-RAG-001
 * Invariant coverage:  INV-SCOPE-001/002/004/005 (scope status rendered verbatim,
 *                      separate from tutor response), INV-CITE-001 (citations only by
 *                      server-provided source_id, never synthesized).
 * ADR: ADR-005 (validated structured response contract)
 *
 * Element under test: ChatPage, ModeSelector, ChatMessage, SourceCitation, WritingFeedback
 * (production modules are created in Gate 3; imports fail until then by design).
 */
import { describe, it, expect, beforeAll, afterAll, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { axe } from "jest-axe";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";

import { handlers } from "./msw/handlers";
import ChatPage from "../pages/ChatPage";

const server = setupServer(...handlers);

beforeAll(() => server.listen({ onUnhandledFrame: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function renderChat() {
  return render(
    <MemoryRouter>
      <ChatPage />
    </MemoryRouter>,
  );
}

const lessonResponse = {
  task: "lesson_help",
  abstained: false,
  source_ids: ["chunk_12"],
  answer: "Use the present perfect for experiences.",
  sources: [{ source_id: "chunk_12", title: "Present Perfect", section: "Form" }],
  validation_id: "val_001",
};

describe("learner mode selection maps to the correct tutor path", () => {
  it("FR-CHAT-001: all five learner modes are offered", () => {
    renderChat();
    for (const mode of [
      /conversation practice/i,
      /writing feedback/i,
      /grammar question/i,
      /vocabulary question/i,
      /lesson question/i,
    ]) {
      expect(screen.getByRole("radio", { name: mode })).toBeInTheDocument();
    }
  });

  it("FR-CHAT-001: sending in conversation_practice posts learner_mode to chat", async () => {
    let received: Record<string, unknown> | null = null;
    server.use(
      http.post("/api/sessions", () => HttpResponse.json({ session_id: "s1" }, { status: 200 })),
      http.post("/api/sessions/:id/messages", async ({ request }) => {
        received = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(
          { task: "conversation", abstained: false, source_ids: [], answer: "Hello!", validation_id: "v1" },
          { status: 200 },
        );
      }),
    );
    renderChat();
    fireEvent.click(screen.getByRole("radio", { name: /conversation practice/i }));
    fireEvent.change(screen.getByLabelText(/message/i), { target: { value: "Hi tutor" } });
    fireEvent.click(screen.getByRole("button", { name: /send/i }));
    await waitFor(() => expect(received?.learner_mode).toBe("conversation_practice"));
    expect(await screen.findByText("Hello!")).toBeInTheDocument();
  });
});

describe("INV-SCOPE-002/004/005 scope status rendered verbatim and separate", () => {
  it("INV-SCOPE-002: an off-topic rejection shows the exact fixed refusal with no tutor answer", async () => {
    const refusal = "I'm sorry, but I can only help with language-learning questions.";
    server.use(
      http.post("/api/sessions", () => HttpResponse.json({ session_id: "s1" }, { status: 200 })),
      http.post("/api/sessions/:id/messages", () =>
        HttpResponse.json(
          { scope_status: "rejected", scope_message: refusal, answer: "" },
          { status: 200 },
        ),
      ),
    );
    renderChat();
    fireEvent.click(screen.getByRole("radio", { name: /conversation practice/i }));
    fireEvent.change(screen.getByLabelText(/message/i), { target: { value: "tell me a joke" } });
    fireEvent.click(screen.getByRole("button", { name: /send/i }));
    expect(await screen.findByText(refusal)).toBeInTheDocument();
    expect(screen.getByRole("status", { name: /scope/i })).toHaveTextContent("rejected");
  });

  it("INV-SCOPE-004: uncertain scope status is shown independently of any answer", async () => {
    server.use(
      http.post("/api/sessions", () => HttpResponse.json({ session_id: "s1" }, { status: 200 })),
      http.post("/api/sessions/:id/messages", () =>
        HttpResponse.json(
          { scope_status: "uncertain", scope_message: "Could you rephrase your question?", answer: "" },
          { status: 200 },
        ),
      ),
    );
    renderChat();
    fireEvent.click(screen.getByRole("radio", { name: /conversation practice/i }));
    fireEvent.change(screen.getByLabelText(/message/i), { target: { value: "what about that thing" } });
    fireEvent.click(screen.getByRole("button", { name: /send/i }));
    expect(await screen.findByRole("status", { name: /scope/i })).toHaveTextContent("uncertain");
  });
});

describe("INV-CITE-001 citations", () => {
  it("INV-CITE-001: lesson_help renders citations from server source metadata", async () => {
    server.use(
      http.post("/api/sessions", () => HttpResponse.json({ session_id: "s1" }, { status: 200 })),
      http.post("/api/sessions/:id/messages", () => HttpResponse.json(lessonResponse, { status: 200 })),
    );
    renderChat();
    fireEvent.click(screen.getByRole("radio", { name: /grammar question/i }));
    fireEvent.change(screen.getByLabelText(/message/i), { target: { value: "when do I use present perfect" } });
    fireEvent.click(screen.getByRole("button", { name: /send/i }));
    expect(await screen.findByText(/present perfect/i)).toBeInTheDocument();
    expect(screen.getByText(/form/i)).toBeInTheDocument();
  });

  it("INV-CITE-001: a source_id absent from metadata is not rendered (never synthesized)", async () => {
    server.use(
      http.post("/api/sessions", () => HttpResponse.json({ session_id: "s1" }, { status: 200 })),
      http.post("/api/sessions/:id/messages", () =>
        HttpResponse.json(
          {
            task: "lesson_help",
            abstained: false,
            source_ids: ["ghost_id"],
            answer: "Answer text.",
            sources: [],
            validation_id: "v1",
          },
          { status: 200 },
        ),
      ),
    );
    renderChat();
    fireEvent.click(screen.getByRole("radio", { name: /lesson question/i }));
    fireEvent.change(screen.getByLabelText(/message/i), { target: { value: "explain articles" } });
    fireEvent.click(screen.getByRole("button", { name: /send/i }));
    await screen.findByText("Answer text.");
    expect(screen.queryByText(/ghost_id/)).not.toBeInTheDocument();
  });

  it("INV-CITE-001: abstained=true shows limitation text and no citations", async () => {
    server.use(
      http.post("/api/sessions", () => HttpResponse.json({ session_id: "s1" }, { status: 200 })),
      http.post("/api/sessions/:id/messages", () =>
        HttpResponse.json(
          {
            task: "lesson_help",
            abstained: true,
            source_ids: [],
            answer: "I don't have enough evidence in the approved lessons to answer that.",
            sources: [],
            validation_id: "v1",
          },
          { status: 200 },
        ),
      ),
    );
    renderChat();
    fireEvent.click(screen.getByRole("radio", { name: /lesson question/i }));
    fireEvent.change(screen.getByLabelText(/message/i), { target: { value: "rare edge grammar" } });
    fireEvent.click(screen.getByRole("button", { name: /send/i }));
    expect(await screen.findByText(/not have enough evidence/i)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /source/i })).not.toBeInTheDocument();
  });
});

describe("FR-FEED-001 writing feedback", () => {
  it("FR-FEED-001: writing_feedback preserves the original and shows the suggestion separately", async () => {
    const original = "She go to school everyday.";
    server.use(
      http.post("/api/sessions", () => HttpResponse.json({ session_id: "s1" }, { status: 200 })),
      http.post("/api/sessions/:id/messages", () =>
        HttpResponse.json(
          {
            task: "writing_feedback",
            abstained: false,
            source_ids: [],
            answer: "Adjust subject-verb agreement.",
            suggested_text: "She goes to school every day.",
            explanation: "Third-person singular needs -es.",
            examples: ["He goes to work."],
            validation_id: "v1",
          },
          { status: 200 },
        ),
      ),
    );
    renderChat();
    fireEvent.click(screen.getByRole("radio", { name: /writing feedback/i }));
    fireEvent.change(screen.getByLabelText(/message/i), { target: { value: original } });
    fireEvent.click(screen.getByRole("button", { name: /send/i }));
    expect(await screen.findByText(original)).toBeInTheDocument();
    expect(await screen.findByText(/she goes to school every day/i)).toBeInTheDocument();
  });
});

describe("VS-16 accessibility", () => {
  it("VS-16: conversation chat page has zero critical axe violations", async () => {
    const { container } = renderChat();
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("VS-16: writing feedback view has zero critical axe violations", async () => {
    const original = "She go to school everyday.";
    server.use(
      http.post("/api/sessions", () => HttpResponse.json({ session_id: "s1" }, { status: 200 })),
      http.post("/api/sessions/:id/messages", () =>
        HttpResponse.json(
          {
            task: "writing_feedback",
            abstained: false,
            source_ids: [],
            answer: "Adjust subject-verb agreement.",
            suggested_text: "She goes to school every day.",
            explanation: "Third-person singular needs -es.",
            examples: ["He goes to work."],
            validation_id: "v1",
          },
          { status: 200 },
        ),
      ),
    );
    const { container } = renderChat();
    fireEvent.click(screen.getByRole("radio", { name: /writing feedback/i }));
    fireEvent.change(screen.getByLabelText(/message/i), { target: { value: original } });
    fireEvent.click(screen.getByRole("button", { name: /send/i }));
    await screen.findByText(/she goes to school every day/i);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
