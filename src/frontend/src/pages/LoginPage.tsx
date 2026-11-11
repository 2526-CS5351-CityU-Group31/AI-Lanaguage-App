/**
 * LoginPage - login and registration form.
 *
 * Element: frontend auth page
 * Implements: FR-AUTH-001; INV-LANG-001, INV-AUTH-001; ADR-009
 *
 * No language selector is rendered; the language is fixed to 'en'. The session
 * token returned by the backend is stored in memory by AuthContext.
 * Registration defaults the CEFR level to A1 (no new selector in this task) and
 * already returns a session token, so login is not called again after register.
 */
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";

type View = "login" | "register";

export default function LoginPage() {
  const navigate = useNavigate();
  const { login, register } = useAuth();
  const [view, setView] = useState<View>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setMessage(null);
    setFieldErrors({});
    try {
      if (view === "register") {
        await register({ email, password, cefr_level: "A1", language: "en" });
      } else {
        await login({ email, password });
      }
      navigate("/chat");
    } catch (err) {
      if (err instanceof ApiError) {
        setMessage(err.message);
        setFieldErrors(err.fieldErrors ?? {});
      } else {
        setMessage("Something went wrong. Please try again.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="page login-page">
      <h1>{view === "login" ? "Log in" : "Create account"}</h1>
      <form onSubmit={handleSubmit} aria-label={view === "login" ? "Log in" : "Register"}>
        {message ? (
          <p role="alert" className="form-error">
            {message}
          </p>
        ) : null}

        <label htmlFor="email" className="field">
          <span>Email</span>
          <input
            id="email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            aria-invalid={fieldErrors.email ? true : undefined}
          />
          {fieldErrors.email ? <span className="field-error">{fieldErrors.email}</span> : null}
        </label>

        <label htmlFor="password" className="field">
          <span>Password</span>
          <input
            id="password"
            type="password"
            autoComplete={view === "login" ? "current-password" : "new-password"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            aria-invalid={fieldErrors.password ? true : undefined}
          />
          {fieldErrors.password ? (
            <span className="field-error">{fieldErrors.password}</span>
          ) : null}
        </label>

        <button type="submit" disabled={submitting}>
          {submitting ? "Please wait…" : view === "login" ? "Log in" : "Create account"}
        </button>
      </form>

      <button
        type="button"
        className="link-button"
        onClick={() => setView(view === "login" ? "register" : "login")}
      >
        {view === "login" ? "Need an account? Register" : "Already registered? Log in"}
      </button>
    </main>
  );
}
