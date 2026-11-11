/**
 * Typed fetch client for the learner UI.
 *
 * Element: frontend API client (display layer only)
 * Implements: FR-AUTH-001; INV-AUTH-001, ADR-009
 *
 * Sends an in-memory Bearer session token via the `Authorization` header when a
 * token is present. The token is held in module memory only and is never
 * persisted to localStorage, sessionStorage, IndexedDB, cookies, URL
 * parameters, or source files. A browser refresh may therefore clear the
 * session, which is acceptable for this temporary integration adapter. The
 * client never sends a client-chosen user_id.
 */
import type { ApiErrorBody } from "./types";

export const API_BASE = "/api";

let sessionToken: string | null = null;

/**
 * Set or clear the in-memory session token.
 * Passing null (e.g. on logout) removes the Authorization header from future
 * requests. Never persists anywhere.
 */
export function setSessionToken(token: string | null): void {
  sessionToken = token;
}

/** Current in-memory token (exposed for tests and diagnostics only). */
export function getSessionToken(): string | null {
  return sessionToken;
}

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
  if (sessionToken) {
    headers["Authorization"] = `Bearer ${sessionToken}`;
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method,
      headers,
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
    throw new ApiError(response.status, normalizeErrorBody(data, response.status));
  }

  return data as T;
}

/**
 * Normalize non-canonical backend error payloads into the canonical ApiError
 * body shape. Handles:
 * - Canonical {error_code, message, field_errors}
 * - Deployed {"error": "..."} responses
 * - FastAPI {"detail": "..."} or {"detail": [{loc, msg}]} validation responses
 * Never surfaces raw stack traces or `undefined`.
 */
function normalizeErrorBody(data: unknown, status: number): ApiErrorBody {
  const fallbackMessage = `Request failed (${status}).`;

  if (!data || typeof data !== "object") {
    return { error_code: "http_error", message: fallbackMessage };
  }

  const record = data as Record<string, unknown>;

  // Canonical shape.
  if (typeof record.error_code === "string" && typeof record.message === "string") {
    return {
      error_code: record.error_code,
      message: record.message,
      field_errors:
        record.field_errors && typeof record.field_errors === "object"
          ? (record.field_errors as Record<string, string>)
          : undefined,
    };
  }

  // Deployed backend: {"error": "..."}.
  if (typeof record.error === "string" && record.error.trim().length > 0) {
    return { error_code: "error", message: record.error };
  }

  // FastAPI validation: {"detail": [...]} or {"detail": "..."}.
  if (typeof record.detail === "string" && record.detail.trim().length > 0) {
    return { error_code: "detail", message: record.detail };
  }
  if (Array.isArray(record.detail)) {
    const fieldErrors: Record<string, string> = {};
    const messages: string[] = [];
    for (const item of record.detail) {
      if (item && typeof item === "object") {
        const entry = item as Record<string, unknown>;
        const msg = typeof entry.msg === "string" ? entry.msg : undefined;
        const loc = Array.isArray(entry.loc) ? entry.loc.join(".") : undefined;
        if (msg) {
          messages.push(msg);
          if (loc) fieldErrors[loc] = msg;
        }
      }
    }
    return {
      error_code: "validation_error",
      message: messages.join("; ") || "Validation failed.",
      field_errors: Object.keys(fieldErrors).length > 0 ? fieldErrors : undefined,
    };
  }

  // Unknown object without a usable message.
  if (typeof record.message === "string" && record.message.trim().length > 0) {
    return { error_code: "http_error", message: record.message };
  }

  return { error_code: "http_error", message: fallbackMessage };
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}
