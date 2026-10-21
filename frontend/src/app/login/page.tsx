"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const router = useRouter();
  const { signIn, isExpired } = useAuth();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await signIn(email, password);
      router.push("/chat");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Sign-in failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center p-4">
      <div className="max-w-md w-full bg-white rounded-2xl border border-slate-200 shadow-xs p-8 space-y-6">
        <div className="text-center space-y-1">
          <div className="w-10 h-10 rounded-xl bg-indigo-600 text-white flex items-center justify-center text-xl font-bold mx-auto">✈</div>
          <h1 className="text-2xl font-bold text-slate-900">Sign in to PolicyPilot</h1>
          <p className="text-sm text-slate-600">Enterprise AI-Powered Policy Assistant</p>
        </div>
        {isExpired && <div role="status" className="p-3 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-800">Your session has expired. Please sign in again.</div>}
        {error && <div role="alert" className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700">{error}</div>}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="email" className="block text-xs font-semibold text-slate-700 mb-1">Email</label>
            <input id="email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="user@example.com" className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg" />
          </div>
          <div>
            <label htmlFor="password" className="block text-xs font-semibold text-slate-700 mb-1">Password</label>
            <input id="password" type="password" required value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg" />
          </div>
          <button type="submit" disabled={loading} className="w-full py-2.5 px-4 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold rounded-lg transition-colors">
            {loading ? "Signing in..." : "Sign In"}
          </button>
        </form>
      </div>
    </div>
  );
}
