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
  clearAccessToken,
  getAccessToken,
  setAccessToken,
  setUnauthorizedHandler,
  unsetUnauthorizedHandler,
} from "../services/api";
import { fetchMe, login as apiLogin } from "../services/documents";
import type { LoginResponse, MeResponse } from "../types/api";

interface AuthContextValue {
  token: string | null;
  user: MeResponse["user"] | null;
  memberships: MeResponse["memberships"];
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => getAccessToken());
  const [user, setUser] = useState<MeResponse["user"] | null>(null);
  const [memberships, setMemberships] = useState<MeResponse["memberships"]>([]);
  const [loading, setLoading] = useState<boolean>(() => token !== null);

  const logout = useCallback(() => {
    clearAccessToken();
    setToken(null);
    setUser(null);
    setMemberships([]);
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(logout);
    return () => unsetUnauthorizedHandler();
  }, [logout]);

  useEffect(() => {
    if (!token) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    fetchMe()
      .then((me) => {
        if (cancelled) return;
        setUser(me.user);
        setMemberships(me.memberships);
      })
      .catch(() => {
        if (!cancelled) logout();
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token, logout]);

  const login = useCallback(async (email: string, password: string) => {
    const response: LoginResponse = await apiLogin(email, password);
    setAccessToken(response.access_token);
    setToken(response.access_token);
    const me = await fetchMe();
    setUser(me.user);
    setMemberships(me.memberships);
  }, []);

  const value = useMemo(
    () => ({ token, user, memberships, loading, login, logout }),
    [token, user, memberships, loading, login, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}