/**
 * Vocabulary review flow tests (test-only).
 *
 * Requirement coverage: FR-VOC-001, FR-VOC-002
 * ADR: ADR-008 (event-sourced progress - familiarity changes emit events server-side)
 *
 * Element under test: VocabularyPage, VocabularyCard
 * Provisional contract: vocabulary field names are UNCONFIRMED; the plan uses
 * definition_en / example_en unless the backend specifies otherwise.
 * (production modules are created in Gate 3; imports fail until then by design).
 */
import { describe, it, expect, beforeAll, afterAll, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { axe } from "jest-axe";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";

import { handlers } from "./msw/handlers";
import VocabularyPage from "../pages/VocabularyPage";

const server = setupServer(...handlers);

beforeAll(() => server.listen({ onUnhandledFrame: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function renderVocab() {
  return render(
    <MemoryRouter>
      <VocabularyPage />
    </MemoryRouter>,
  );
}

describe("FR-VOC-001 random vocabulary", () => {
  it("FR-VOC-001: renders definition_en and example_en from the backend", async () => {
    renderVocab();
    expect(await screen.findByText("resilient")).toBeInTheDocument();
    expect(screen.getByText(/able to recover quickly from difficulty/i)).toBeInTheDocument();
    expect(screen.getByText(/stayed resilient after the setback/i)).toBeInTheDocument();
  });

  it("FR-VOC-001: an empty vocabulary set shows an empty state, not a crash", async () => {
    server.use(http.get("/api/vocabulary/random", () => HttpResponse.json([], { status: 200 })));
    renderVocab();
    expect(await screen.findByText(/no vocabulary/i)).toBeInTheDocument();
  });

  it("FR-VOC-001: a backend failure shows an error/retry state", async () => {
    server.use(
      http.get("/api/vocabulary/random", () =>
        HttpResponse.json({ error_code: "server_error", message: "Unavailable." }, { status: 500 }),
      ),
    );
    renderVocab();
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});

describe("FR-VOC-002 familiarity state", () => {
  it("FR-VOC-002: submits a familiarity state to POST /me/vocabulary/{entry_id}", async () => {
    const received: { state?: string; entryId?: string } = {};
    server.use(
      http.post("/api/me/vocabulary/:entryId", async ({ request, params }) => {
        const body = (await request.json()) as { state?: string };
        received.state = body.state;
        received.entryId = String(params.entryId);
        return HttpResponse.json({ entry_id: params.entryId, state: body.state }, { status: 200 });
      }),
    );
    renderVocab();
    await screen.findByText("resilient");
    fireEvent.click(screen.getByRole("button", { name: /mastered/i }));
    await waitFor(() => expect(received.state).toBe("mastered"));
    expect(received.entryId).toBe("voc_001");
  });

  it("FR-VOC-002: a rejected invalid state surfaces a 422 error", async () => {
    server.use(
      http.post("/api/me/vocabulary/:entryId", () =>
        HttpResponse.json(
          {
            error_code: "invalid_state",
            message: "Unknown familiarity state.",
            field_errors: { state: "Invalid state." },
          },
          { status: 422 },
        ),
      ),
    );
    renderVocab();
    await screen.findByText("resilient");
    fireEvent.click(screen.getByRole("button", { name: /familiar/i }));
    expect(await screen.findByText(/invalid state/i)).toBeInTheDocument();
  });
});

describe("VS-16 accessibility", () => {
  it("VS-16: vocabulary page has zero critical axe violations", async () => {
    const { container } = renderVocab();
    await screen.findByText("resilient");
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
