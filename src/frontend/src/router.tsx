/**
 * Router - browser router wiring for the learner UI.
 *
 * Element: frontend routing
 * Implements: FR-AUTH-001; ADR-009
 */
import { BrowserRouter } from "react-router-dom";
import type { ReactNode } from "react";

export function AppRouter({ children }: { children: ReactNode }) {
  return <BrowserRouter>{children}</BrowserRouter>;
}
