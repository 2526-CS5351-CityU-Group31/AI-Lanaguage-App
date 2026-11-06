/**
 * Progress API adapter.
 *
 * Element: frontend progress client
 * Implements: FR-DASH-001; INV-PROG-001; ADR-008
 *
 * Renders server-projected aggregates verbatim; performs no client arithmetic.
 */
import { apiRequest } from "./client";
import type { DashboardMetrics } from "./types";

export function getProgress(): Promise<DashboardMetrics> {
  return apiRequest<DashboardMetrics>("/me/progress");
}
