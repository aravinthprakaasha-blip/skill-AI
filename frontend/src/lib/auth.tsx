"use client";
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getToken, setToken } from "./api";

export type Me = {
  id: string;
  email: string;
  display_name: string;
  role: "learner" | "recruiter" | "admin";
  profile_id: string | null;
  public_id: string | null;
  onboarded: boolean;
};

type Ctx = {
  me: Me | null;
  loading: boolean;
  refresh: () => Promise<Me | null>;
  signIn: (token: string, me: Me) => void;
  signOut: () => void;
};

const AuthContext = createContext<Ctx | null>(null);

export function homeFor(me: Me) {
  if (me.role === "admin") return "/admin";
  if (me.role === "recruiter") return "/recruiter";
  return me.onboarded ? "/dashboard" : "/onboarding";
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    if (!getToken()) {
      setMe(null);
      setLoading(false);
      return null;
    }
    try {
      const m = await api<Me>("/api/auth/me");
      setMe(m);
      return m;
    } catch {
      setMe(null);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const signIn = (token: string, m: Me) => {
    setToken(token);
    setMe(m);
  };
  const signOut = () => {
    setToken(null);
    setMe(null);
  };
  return <AuthContext.Provider value={{ me, loading, refresh, signIn, signOut }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth outside AuthProvider");
  return ctx;
}

/** Redirects unauthenticated users (or users with the wrong role) away from a page. */
export function useRequireRole(roles: Me["role"][]) {
  const { me, loading } = useAuth();
  const router = useRouter();
  useEffect(() => {
    if (loading) return;
    if (!me) router.replace("/login");
    else if (!roles.includes(me.role)) router.replace(homeFor(me));
  }, [me, loading, router, roles]);
  return { me, ready: !loading && !!me && roles.includes(me.role) };
}
