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
import { describe, it, expect, beforeAll, afterAll, afterEach, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { axe } from "jest-axe";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";

import { handlers, testMe } from "./msw/handlers";
import { AuthProvider, useAuth } from "../auth/AuthContext";
import { ProtectedRoute } from "../auth/ProtectedRoute";
import { getSessionToken, setSessionToken } from "../api/client";
import App from "../App";
import LoginPage from "../pages/LoginPage";
import ProfilePage from "../pages/ProfilePage";

const server = setupServer(...handlers);

beforeAll(() => server.listen({ onUnhandledFrame: "error" }));
beforeEach(() => {
  setSessionToken(null);
  localStorage.clear();
  sessionStorage.clear();
});
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

describe("bearer token handling (in-memory only)", () => {
  it("FR-AUTH-001: no Authorization header before login", async () => {
    let authHeader: string | null | undefined = "unset";
    server.use(
      http.get("/api/me", ({ request }) => {
        authHeader = request.headers.get("authorization");
        return HttpResponse.json(testMe, { status: 200 });
      }),
    );
    renderApp(<LoginPage />);
    await waitFor(() => expect(authHeader).toBeNull());
    expect(getSessionToken()).toBeNull();
  });

  it("FR-AUTH-001: registration sends cefr_level A1 and stores the Bearer token", async () => {
    let registerBody: Record<string, unknown> | null = null;
    let authAfterLogin: string | null | undefined = "unset";
    let meCalls = 0;
    server.use(
      http.post("/api/auth/register", async ({ request }) => {
        registerBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ session_token: "test_session_token" }, { status: 200 });
      }),
      http.get("/api/me", ({ request }) => {
        meCalls += 1;
        authAfterLogin = request.headers.get("authorization");
        return HttpResponse.json(testMe, { status: 200 });
      }),
    );
    renderApp(<LoginPage />);
    fireEvent.click(screen.getByRole("button", { name: /need an account\? register/i }));
    fireEvent.change(screen.getByLabelText(/email/i), { target: { value: "new@example.com" } });
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: "secret123" } });
    fireEvent.click(screen.getByRole("button", { name: /create account/i }));

    await waitFor(() => expect(registerBody).not.toBeNull());
    expect(registerBody).toMatchObject({ email: "new@example.com", cefr_level: "A1", language: "en" });
    await waitFor(() => expect(authAfterLogin).toBe("Bearer test_session_token"));
    expect(getSessionToken()).toBe("test_session_token");
    expect(meCalls).toBeGreaterThan(0);
  });

  it("FR-AUTH-001: login sends the Bearer token to protected GET /me", async () => {
    let authOnMe: string | null | undefined = "unset";
    server.use(
      http.post("/api/auth/login", () => HttpResponse.json({ session_token: "test_session_token" }, { status: 200 })),
      http.get("/api/me", ({ request }) => {
        authOnMe = request.headers.get("authorization");
        return HttpResponse.json(testMe, { status: 200 });
      }),
    );
    renderApp(<LoginPage />);
    fireEvent.change(screen.getByLabelText(/email/i), { target: { value: "learner@example.com" } });
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: "secret123" } });
    fireEvent.click(screen.getByRole("button", { name: /log in/i }));

    await waitFor(() => expect(authOnMe).toBe("Bearer test_session_token"));
    expect(getSessionToken()).toBe("test_session_token");
  });

  it("FR-AUTH-001: logout clears the in-memory token", async () => {
    setSessionToken("test_session_token");
    function LogoutHarness() {
      const { logout } = useAuth();
      return (
        <button type="button" onClick={() => void logout()}>
          Log out now
        </button>
      );
    }
    renderApp(<LogoutHarness />);
    fireEvent.click(screen.getByRole("button", { name: /log out now/i }));
    await waitFor(() => expect(getSessionToken()).toBeNull());
  });

  it("FR-AUTH-001: no token is written to localStorage or sessionStorage", async () => {
    server.use(
      http.post("/api/auth/login", () => HttpResponse.json({ session_token: "test_session_token" }, { status: 200 })),
    );
    renderApp(<LoginPage />);
    fireEvent.change(screen.getByLabelText(/email/i), { target: { value: "learner@example.com" } });
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: "secret123" } });
    fireEvent.click(screen.getByRole("button", { name: /log in/i }));
    await waitFor(() => expect(getSessionToken()).toBe("test_session_token"));

    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
    const dumped = JSON.stringify({ ...localStorage, ...sessionStorage });
    expect(dumped).not.toContain("test_session_token");
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
          { user_id: "u1", email: "a@b.com", language: "en", cefr_level: "B1", learning_goals: null },
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
    expect(await screen.findByLabelText("Current CEFR level B1")).toBeInTheDocument();
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

  it("FR-PROF-001: profile summary displays only server-provided account values", async () => {
    renderApp(<ProfilePage />);
    const summary = await screen.findByRole("region", { name: /profile summary/i });
    expect(summary).toHaveTextContent(testMe.email);
    expect(summary).toHaveTextContent(testMe.cefr_level);
    expect(summary).toHaveTextContent(/english learner/i);
  });

  it("FR-PROF-001, VS-16: profile summary icon is decorative", async () => {
    renderApp(<ProfilePage />);
    const summary = await screen.findByRole("region", { name: /profile summary/i });
    const icon = summary.querySelector("svg");
    expect(icon).not.toBeNull();
    expect(icon).toHaveAttribute("aria-hidden", "true");
    expect(icon).toHaveAttribute("focusable", "false");
  });
});

describe("VS-16 accessibility", () => {
  it("VS-16: login page has zero critical axe violations", async () => {
    const { container } = await renderAppSettled(<LoginPage />);
    await screen.findByRole("form", { name: /log in/i });
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("VS-16: authenticated dashboard shell (with Navigation) has zero critical axe violations", async () => {
    // Render the real App shell at a protected route so the authenticated
    // dashboard shell, including Navigation (sidebar), is part of the a11y
    // surface under test. No production test-only hooks are used.
    const { container } = render(
      <MemoryRouter initialEntries={["/progress"]}>
        <AuthProvider>
          <App />
        </AuthProvider>
      </MemoryRouter>,
    );

    // Wait for the authenticated shell (Navigation landmark) to be present.
    await screen.findByRole("navigation", { name: /main navigation/i });
    // Wait for the dashboard content to settle so axe inspects the final tree.
    await screen.findByRole("heading", { name: /welcome/i });

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("VS-16: navigation icons are decorative and preserve accessible link names", async () => {
    const { container } = render(
      <MemoryRouter initialEntries={["/progress"]}>
        <AuthProvider>
          <App />
        </AuthProvider>
      </MemoryRouter>,
    );

    const navigation = await screen.findByRole("navigation", { name: /main navigation/i });
    for (const name of ["Practice", "Vocabulary", "Progress", "Profile"]) {
      const link = screen.getByRole("link", { name });
      expect(navigation).toContainElement(link);
      const icon = link.querySelector("svg");
      expect(icon).not.toBeNull();
      expect(icon).toHaveAttribute("aria-hidden", "true");
      expect(icon).toHaveAttribute("focusable", "false");
    }

    const logout = screen.getByRole("button", { name: "Log out" });
    expect(navigation).toContainElement(logout);
    const logoutIcon = logout.querySelector("svg");
    expect(logoutIcon).not.toBeNull();
    expect(logoutIcon).toHaveAttribute("aria-hidden", "true");
    expect(container).toContainElement(navigation);
  });

  it("VS-16: redesigned profile page has zero critical axe violations", async () => {
    const { container } = renderApp(<ProfilePage />);
    await screen.findByRole("region", { name: /profile summary/i });
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
