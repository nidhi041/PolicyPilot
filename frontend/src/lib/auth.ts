export interface AuthUser { id: string; email: string; }
export interface UserProfile { id: string; role: string; region: string; is_hr_administrator: boolean; }
export interface AuthSession { access_token: string; refresh_token?: string; expires_at: number; user: AuthUser; profile?: UserProfile; }

export const SESSION_KEY = "policypilot_session";
export const isSessionExpired = (s: AuthSession | null, now = Date.now() / 1000): boolean => !s?.expires_at || now >= s.expires_at;

export function saveSession(s: AuthSession): void {
  if (typeof window !== "undefined") localStorage.setItem(SESSION_KEY, JSON.stringify(s));
}
export function loadSession(): AuthSession | null {
  try { return typeof window !== "undefined" ? JSON.parse(localStorage.getItem(SESSION_KEY) || "") : null; } catch { return null; }
}
export function clearSession(): void {
  if (typeof window !== "undefined") localStorage.removeItem(SESSION_KEY);
}

export async function fetchUserProfile(token: string): Promise<UserProfile> {
  const base = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
  const r = await fetch(`${base}/api/v1/auth/me`, { headers: { Authorization: `Bearer ${token}` } });
  if (!r.ok) throw new Error("Profile verification failed");
  return (await r.json()).profile;
}

export async function signInWithPassword(email: string, pass: string): Promise<AuthSession> {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !key) throw new Error("Supabase auth credentials are not configured");
  const r = await fetch(`${url.replace(/\/$/, "")}/auth/v1/token?grant_type=password`, {
    method: "POST",
    headers: { "Content-Type": "application/json", apikey: key },
    body: JSON.stringify({ email, password: pass }),
  });
  if (!r.ok) throw new Error("Invalid credentials");
  const d = await r.json();
  const session: AuthSession = {
    access_token: d.access_token,
    expires_at: d.expires_at || Math.floor(Date.now() / 1000) + (d.expires_in || 3600),
    user: { id: d.user.id, email: d.user.email },
  };
  try { session.profile = await fetchUserProfile(session.access_token); } catch {
    session.profile = { id: session.user.id, role: "employee", region: "GLOBAL", is_hr_administrator: false };
  }
  return session;
}

export async function signOutSupabase(token?: string): Promise<void> {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (url && key && token) {
    await fetch(`${url.replace(/\/$/, "")}/auth/v1/logout`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, apikey: key },
    }).catch(() => {});
  }
  clearSession();
}
