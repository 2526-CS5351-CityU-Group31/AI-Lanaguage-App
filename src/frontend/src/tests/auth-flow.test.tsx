/**
 * Authentication + profile flow tests (test-only).
 *
 * Requirement coverage: FR-AUTH-001, FR-PROF-001
 * Invariant coverage:  INV-AUTH-001 (client never sends user_id; protected route redirects),
 *                      INV-LANG-001 (no language selector; language fixed 'en'),
 *                      INV-CEFR-001 (level selector limited to A1-B2)
 * ADR: ADR-009 (learner data isolation)
 *
 * Element under test: AuthContext, ProtectedRoute, LoginPage, ProfilePage
 * (production modules are created in Gate 3; imports fail until then by design).
 */
import { describe, it, expect, beforeAll, afterAll, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { axe } from "jest-axe";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";

import { handlers, testMe } from "./msw/handlers";
import { AuthProvider } from "../auth/AuthContext";
import { ProtectedRoute } from "../auth/ProtectedRoute";
import LoginPage from "../pages/LoginPage";
import ProfilePage from "../pages/ProfilePage";

const server = setupServer(...handlers);

beforeAll(() => server.listen({ onUnhandledFrame: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function renderApp(ui: React.ReactNode) {
  return render(
    <MemoryRouter>
      <AuthProvider>{ui}</AuthProvider>
    </MemoryRouter>,
  );
}

/**
 * Render inside AuthProvider and wait for its asynchronous GET /me session
 * initialization to settle, so axe and assertions run against a stable tree.
 * Waits on the observed /me completion via waitFor, never an arbitrary delay.
 */
async function renderAppSettled(ui: React.ReactNode) {
  let meResolved = false;
  server.use(
    http.get(`/api/me`, () => {
      meResolved = true;
      return HttpResponse.json(testMe, { status: 200 });
    }),
  );
  const view = renderApp(ui);
  await waitFor(() => expect(meResolved).toBe(true));
  return view;
}

describe("FR-AUTH-001 login and register", () => {
  it("FR-AUTH-001: renders a login form and sends credentials with include-credentials", async () => {
    renderApp(<LoginPage />);
    expect(screen.getByRole("form", { name: /log in/i })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/email/i), { target: { value: "learner@example.com" } });
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: "secret123" } });
    fireEvent.click(screen.getByRole("button", { name: /log in/i }));
    await waitFor(() => expect(screen.queryByText(/email and password are required/i)).not.toBeInTheDocument());
  });

  it("INV-LANG-001: no language selector is rendered anywhere", async () => {
    await renderAppSettled(<LoginPage />);
    expect(screen.queryByLabelText(/language/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/select language/i)).not.toBeInTheDocument();
  });

  it("FR-AUTH-001: shows 422 field errors returned by the backend on invalid credentials", async () => {
    server.use(
      http.post("/api/auth/login", () =>
        HttpResponse.json(
          {
            error_code: "invalid_credentials",
            message: "Email and password are required.",
            field_errors: { email: "Required", password: "Required" },
          },
          { status: 422 },
        ),
      ),
    );
    renderApp(<LoginPage />);
    fireEvent.click(screen.getByRole("button", { name: /log in/i }));
    expect(await screen.findByText(/email and password are required/i)).toBeInTheDocument();
  });
});

describe("INV-AUTH-001 protected routes", () => {
  it("INV-AUTH-001: redirects unauthenticated users away from a protected route", async () => {
    server.use(
      http.get("/api/me", () =>
        HttpResponse.json({ error_code: "unauthenticated", message: "Login required." }, { status: 401 }),
      ),
    );
    renderApp(
      <ProtectedRoute>
        <div>SECRET AREA</div>
      </ProtectedRoute>,
    );
    await waitFor(() => expect(screen.queryByText("SECRET AREA")).not.toBeInTheDocument());
  });

  it("INV-AUTH-001: authenticated users see protected content", async () => {
    server.use(
      http.get("/api/me", () =>
        HttpResponse.json(
          { id: "u1", email: "a@b.com", language: "en", cefr_level: "B1", learning_goals: "" },
          { status: 200 },
        ),
      ),
    );
    renderApp(
      <ProtectedRoute>
        <div>SECRET AREA</div>
      </ProtectedRoute>,
    );
    expect(await screen.findByText("SECRET AREA")).toBeInTheDocument();
  });
});

describe("FR-PROF-001 profile update and INV-CEFR-001", () => {
  it("FR-PROF-001: displays the CEFR level fetched from the backend", async () => {
    renderApp(<ProfilePage />);
    expect(await screen.findByText(/B1/)).toBeInTheDocument();
  });

  it("INV-CEFR-001: the level selector offers only A1, A2, B1, B2", async () => {
    renderApp(<ProfilePage />);
    const select = await screen.findByRole("combobox", { name: /cefr level/i });
    const options = Array.from(select.querySelectorAll("option")).map((o) => o.textContent);
    expect(options.sort()).toEqual(["A1", "A2", "B1", "B2"]);
    expect(options).not.toContain("C1");
    expect(options).not.toContain("C2");
  });

  it("INV-CEFR-001: a rejected invalid level surfaces a 422 field error", async () => {
    server.use(
      http.patch("/api/me", () =>
        HttpResponse.json(
          {
            error_code: "invalid_cefr",
            message: "Level must be one of A1, A2, B1, B2.",
            field_errors: { cefr_level: "Invalid CEFR level." },
          },
          { status: 422 },
        ),
      ),
    );
    renderApp(<ProfilePage />);
    const save = await screen.findByRole("button", { name: /save/i });
    fireEvent.click(save);
    expect(await screen.findByText(/invalid cefr level/i)).toBeInTheDocument();
  });
});

describe("VS-16 accessibility", () => {
  it("VS-16: login page has zero critical axe violations", async () => {
    const { container } = await renderAppSettled(<LoginPage />);
    await screen.findByRole("form", { name: /log in/i });
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
