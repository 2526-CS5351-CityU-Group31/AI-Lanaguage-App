/**
 * ProtectedRoute - redirects unauthenticated visitors away from app routes.
 *
 * Element: frontend route guard
 * Implements: FR-AUTH-001; INV-AUTH-001; ADR-009
 *
 * This guard is a usability measure only; the API remains the authoritative
 * boundary for identity and ownership.
 */
import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "./AuthContext";
import LoadingState from "../components/LoadingState";

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();

  if (loading) {
    return <LoadingState label="Checking your session…" />;
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}
