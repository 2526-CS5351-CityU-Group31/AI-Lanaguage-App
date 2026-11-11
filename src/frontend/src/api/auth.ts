/**
 * Authentication API adapter.
 *
 * Element: frontend auth client
 * Implements: FR-AUTH-001; INV-AUTH-001, INV-LANG-001; ADR-009
 */
import { apiRequest } from "./client";
import type { LoginRequest, MeResponse, RegisterRequest, TokenResponse } from "./types";

export function register(payload: RegisterRequest): Promise<TokenResponse> {
  return apiRequest<TokenResponse>("/auth/register", { method: "POST", body: payload });
}

export function login(payload: LoginRequest): Promise<TokenResponse> {
  return apiRequest<TokenResponse>("/auth/login", { method: "POST", body: payload });
}

export function logout(): Promise<unknown> {
  return apiRequest<unknown>("/auth/logout", { method: "POST" });
}

export function getMe(): Promise<MeResponse> {
  return apiRequest<MeResponse>("/me");
}
