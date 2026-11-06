/**
 * Typed fetch client for the learner UI.
 *
 * Element: frontend API client (display layer only)
 * Implements: FR-AUTH-001; INV-AUTH-001, ADR-009
 *
 * Uses HTTP-only session cookies via `credentials: "include"`. Never stores
 * authentication tokens or identity in localStorage/sessionStorage, and never
 * sends a client-chosen user_id.
 */
import type { ApiErrorBody } from "./types";

export const API_BASE = "/api";

export class ApiError extends Error {
  status: number;
  code: string;
  fieldErrors?: Record<string, string>;

  constructor(status: number, body: ApiErrorBody) {
    super(body.message);
    this.name = "ApiError";
    this.status = status;
    this.code = body.error_code;
    this.fieldErrors = body.field_errors;
  }
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  signal?: AbortSignal;
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, signal } = options;

  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method,
      headers,
      credentials: "include",
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    });
  } catch (err) {
    throw new ApiError(0, {
      error_code: "network_error",
      message: "Network error. Please check your connection and try again.",
    });
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const text = await response.text();
  const data = text ? safeJson(text) : null;

  if (!response.ok) {
    const body: ApiErrorBody =
      data && typeof data === "object"
        ? (data as ApiErrorBody)
        : { error_code: "http_error", message: `Request failed (${response.status}).` };
    throw new ApiError(response.status, body);
  }

  return data as T;
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}
