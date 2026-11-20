/**
 * AuthContext - session identity provider.
 *
 * Element: frontend auth context
 * Implements: FR-AUTH-001; INV-AUTH-001; ADR-009
 *
 * The session token is stored in module memory (via setSessionToken) only.
 * Identity is fetched from GET /me (authenticated by the Bearer token). No
 * token or identity is persisted to localStorage/sessionStorage. A browser
 * refresh may clear the session; this is acceptable for the temporary
 * integration adapter.
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
import {
  getMe,
  login as loginApi,
  logout as logoutApi,
  register as registerApi,
} from "../api/auth";
import { ApiError, setSessionToken } from "../api/client";
import type { LoginRequest, MeResponse, RegisterRequest } from "../api/types";

interface AuthContextValue {
  user: MeResponse | null;
  loading: boolean;
  error: string | null;
  login: (payload: LoginRequest) => Promise<void>;
  register: (payload: RegisterRequest) => Promise<void>;
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

  const login = useCallback(
    async (payload: LoginRequest) => {
      try {
        const { session_token } = await loginApi(payload);
        setSessionToken(session_token);
      } catch (err) {
        setSessionToken(null);
        throw err;
      }
      await refresh();
    },
    [refresh],
  );

  const register = useCallback(
    async (payload: RegisterRequest) => {
      try {
        const { session_token } = await registerApi(payload);
        setSessionToken(session_token);
      } catch (err) {
        setSessionToken(null);
        throw err;
      }
      await refresh();
    },
    [refresh],
  );

  const logout = useCallback(async () => {
    try {
      await logoutApi();
    } catch {
      // Ignore backend logout errors; the local session is cleared regardless.
    } finally {
      setSessionToken(null);
      setUser(null);
    }
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ user, loading, error, login, register, logout, refresh }),
    [user, loading, error, login, register, logout, refresh],
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
