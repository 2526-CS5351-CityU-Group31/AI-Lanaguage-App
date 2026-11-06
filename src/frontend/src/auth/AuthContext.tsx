/**
 * AuthContext - session identity provider.
 *
 * Element: frontend auth context
 * Implements: FR-AUTH-001; INV-AUTH-001; ADR-009
 *
 * Identity is fetched from the server (GET /me) and held only in memory.
 * No tokens or identity are persisted to localStorage/sessionStorage.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { getMe, login as loginApi, logout as logoutApi } from "../api/auth";
import { ApiError } from "../api/client";
import type { LoginRequest, MeResponse } from "../api/types";

interface AuthContextValue {
  user: MeResponse | null;
  loading: boolean;
  error: string | null;
  login: (payload: LoginRequest) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<MeResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const me = await getMe();
      setUser(me);
      setError(null);
    } catch (err) {
      setUser(null);
      if (err instanceof ApiError && err.status === 401) {
        setError(null);
      } else {
        setError(err instanceof Error ? err.message : "Unable to load session.");
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const login = useCallback(async (payload: LoginRequest) => {
    await loginApi(payload);
    await refresh();
  }, [refresh]);

  const logout = useCallback(async () => {
    try {
      await logoutApi();
    } finally {
      setUser(null);
    }
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ user, loading, error, login, logout, refresh }),
    [user, loading, error, login, logout, refresh],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return ctx;
}
