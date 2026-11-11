/**
 * Progress dashboard flow tests (test-only).
 *
 * Requirement coverage: FR-DASH-001
 * Invariant coverage:  INV-PROG-001 (dashboard renders backend aggregates verbatim;
 *                      the frontend performs NO arithmetic on progress values)
 * ADR: ADR-008 (event-sourced progress; totals projected server-side)
 *
 * Element under test: ProgressPage
 * (production modules are created in Gate 3; imports fail until then by design).
 */
import { describe, it, expect, beforeAll, afterAll, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { axe } from "jest-axe";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";

import { handlers } from "./msw/handlers";
import ProgressPage from "../pages/ProgressPage";

const server = setupServer(...handlers);

beforeAll(() => server.listen({ onUnhandledFrame: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function renderProgress() {
  return render(
    <MemoryRouter>
      <ProgressPage />
    </MemoryRouter>,
  );
}

describe("FR-DASH-001 dashboard metrics", () => {
  it("FR-DASH-001: renders session and vocabulary totals from the backend", async () => {
    renderProgress();
    expect(await screen.findByText(/sessions/i)).toBeInTheDocument();
    expect(screen.getByTestId("metric-sessions")).toHaveTextContent("7");
    expect(screen.getByTestId("metric-words_reviewed")).toHaveTextContent("42");
    expect(screen.getByTestId("metric-mastered_vocabulary")).toHaveTextContent("11");
  });

  it("INV-PROG-001: renders exact server values with no client-side arithmetic", async () => {
    server.use(
      http.get("/api/me/progress", () =>
        HttpResponse.json(
          { sessions: 3, words_reviewed: 9, mastered_vocabulary: 2, recent_topics: [] },
          { status: 200 },
        ),
      ),
    );
    renderProgress();
    expect(await screen.findByTestId("metric-sessions")).toHaveTextContent("3");
    expect(screen.getByTestId("metric-words_reviewed")).toHaveTextContent("9");
    expect(screen.getByTestId("metric-mastered_vocabulary")).toHaveTextContent("2");
    expect(screen.queryByTestId("metric-sessions")).not.toHaveTextContent("14");
  });

  it("FR-DASH-001: a backend failure shows an error state instead of fabricated numbers", async () => {
    server.use(
      http.get("/api/me/progress", () =>
        HttpResponse.json({ error_code: "server_error", message: "Unavailable." }, { status: 503 }),
      ),
    );
    renderProgress();
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.queryByTestId("metric-sessions")).not.toBeInTheDocument();
  });

  it("FR-DASH-001: unauthenticated access redirects away from the dashboard", async () => {
    server.use(
      http.get("/api/me/progress", () =>
        HttpResponse.json({ error_code: "unauthenticated", message: "Login required." }, { status: 401 }),
      ),
    );
    renderProgress();
    await waitFor(() =>
      expect(screen.queryByTestId("metric-sessions")).not.toBeInTheDocument(),
    );
  });

  it("FR-DASH-001, VS-16: quick-action icons preserve accessible names and routes", async () => {
    renderProgress();
    await screen.findByTestId("metric-sessions");

    const expectedActions = [
      { name: /conversation practice/i, path: "/chat" },
      { name: /writing feedback/i, path: "/chat" },
      { name: /grammar practice/i, path: "/chat" },
      { name: /vocabulary review/i, path: "/vocabulary" },
      { name: /^profile/i, path: "/profile" },
    ];

    for (const action of expectedActions) {
      const link = screen.getByRole("link", { name: action.name });
      expect(link).toHaveAttribute("href", action.path);
      const icon = link.querySelector("svg");
      expect(icon).not.toBeNull();
      expect(icon).toHaveAttribute("aria-hidden", "true");
      expect(icon).toHaveAttribute("focusable", "false");
    }
  });
});

describe("VS-16 accessibility", () => {
  it("VS-16: progress page has zero critical axe violations", async () => {
    const { container } = renderProgress();
    await screen.findByTestId("metric-sessions");
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
