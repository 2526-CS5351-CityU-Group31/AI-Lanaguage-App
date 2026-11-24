/**
 * Entry point for the learner UI.
 *
 * Element: frontend composition root
 * Implements: FR-AUTH-001; ADR-009
 */
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { AuthProvider } from "./auth/AuthContext";
import { AppRouter } from "./router";
import App from "./App";
import "./styles.css";

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("Root element #root not found");
}

createRoot(rootElement).render(
  <StrictMode>
    <AppRouter>
      <AuthProvider>
        <App />
      </AuthProvider>
    </AppRouter>
  </StrictMode>,
);
