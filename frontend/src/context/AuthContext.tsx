"use client";

import React, { createContext, useContext, useState, useEffect, type ReactNode } from "react";
import {
  AuthSession,
  isSessionExpired,
  loadSession,
  saveSession,
  clearSession,
  signInWithPassword,
  signOutSupabase,
  fetchUserProfile,
} from "@/lib/auth";

interface AuthCtx {
  session: AuthSession | null;
  profile: AuthSession["profile"] | null;
  user: AuthSession["user"] | null;
  isLoading: boolean;
  isExpired: boolean;
  signIn: (e: string, p: string) => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthCtx | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<AuthSession | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isExpired, setIsExpired] = useState(false);

  useEffect(() => {
    let active = true;
    (async () => {
      await Promise.resolve();
      if (!active) return;
      const s = loadSession();
      if (!s || isSessionExpired(s)) {
        if (s) { clearSession(); setIsExpired(true); }
        setIsLoading(false);
        return;
      }
      try {
        const p = await fetchUserProfile(s.access_token);
        if (active) { s.profile = p; saveSession(s); }
      } catch {}
      if (active) { setSession(s); setIsLoading(false); }
    })();
    return () => { active = false; };
  }, []);

  const signIn = async (email: string, pass: string) => {
    setIsLoading(true);
    try {
      const s = await signInWithPassword(email, pass);
      saveSession(s);
      setSession(s);
      setIsExpired(false);
    } finally {
      setIsLoading(false);
    }
  };

  const signOut = async () => {
    setIsLoading(true);
    try { await signOutSupabase(session?.access_token); }
    finally { setSession(null); setIsExpired(false); setIsLoading(false); }
  };

  return (
    <AuthContext.Provider value={{ session, profile: session?.profile ?? null, user: session?.user ?? null, isLoading, isExpired, signIn, signOut }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = (): AuthCtx => {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used in AuthProvider");
  return ctx;
};
