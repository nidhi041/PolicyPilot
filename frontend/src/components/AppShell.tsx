"use client";

import React, { useState, useEffect, type ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { getPageTitle, canAccessRoute, getVisibleNavItems } from "./nav-config";
import { useAuth } from "@/context/AuthContext";

export interface AppShellProps {
  children: ReactNode;
  activeRegion?: string;
  userRole?: string;
}

export function AppShell({
  children,
  activeRegion = "GLOBAL",
  userRole = "Employee",
}: AppShellProps) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const pathname = usePathname() || "";
  const router = useRouter();
  const { session, profile, user, isLoading, signOut } = useAuth();

  useEffect(() => {
    if (!isLoading && !session) router.push("/login");
  }, [isLoading, session, router]);

  // Close drawer on Escape key
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMobileOpen(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  if (isLoading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center p-4">
        <div className="w-8 h-8 border-3 border-indigo-600 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }
  if (!session) return null;

  const isHr = Boolean(profile?.is_hr_administrator);
  const allowed = canAccessRoute(pathname, true, isHr);
  const visibleNav = getVisibleNavItems(isHr);
  const pageTitle = getPageTitle(pathname);
  const region = profile?.region || activeRegion;
  const role = profile?.role || userRole;

  return (
    <div className="min-h-screen bg-slate-50 text-slate-800 flex flex-col md:flex-row antialiased">
      {/* Mobile Backdrop */}
      {mobileOpen && (
        <div
          role="presentation"
          className="fixed inset-0 bg-slate-900/40 z-40 md:hidden backdrop-blur-xs transition-opacity"
          onClick={() => setMobileOpen(false)}
        />
      )}

      {/* Sidebar Navigation */}
      <aside
        id="sidebar-nav"
        aria-label="Sidebar navigation"
        className={`fixed inset-y-0 left-0 z-50 w-64 bg-white border-r border-slate-200 flex flex-col transition-transform duration-200 ease-in-out md:static md:translate-x-0 ${
          mobileOpen ? "translate-x-0 shadow-xl" : "-translate-x-full md:shadow-none"
        }`}
      >
        <div className="h-16 px-6 border-b border-slate-200 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2.5 font-bold text-slate-900 text-lg tracking-tight">
            <span className="w-8 h-8 rounded-lg bg-indigo-600 text-white flex items-center justify-center text-base shadow-xs" aria-hidden="true">
              ✈
            </span>
            <span>PolicyPilot</span>
          </Link>
          <button
            type="button"
            className="md:hidden p-1.5 text-slate-500 hover:text-slate-700 rounded-md"
            onClick={() => setMobileOpen(false)}
            aria-label="Close navigation"
          >
            ✕
          </button>
        </div>

        <nav aria-label="Main Navigation" className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
          {visibleNav.map((item) => {
            const isActive = pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setMobileOpen(false)}
                aria-current={isActive ? "page" : undefined}
                className={`flex items-center gap-3 px-3.5 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                  isActive
                    ? "bg-indigo-50 text-indigo-700 shadow-xs"
                    : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                }`}
              >
                <span className="text-base" aria-hidden="true">
                  {item.icon}
                </span>
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>

        <div className="p-4 border-t border-slate-200 bg-slate-50/50 space-y-2">
          <div className="flex items-center justify-between text-xs text-slate-500">
            <span>Jurisdiction</span>
            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800">
              {region}
            </span>
          </div>
          <div className="flex items-center justify-between text-xs text-slate-500">
            <span>Role</span>
            <span className="font-medium text-slate-700 capitalize">{role.replace("_", " ")}</span>
          </div>
          <button type="button" onClick={() => signOut()} className="w-full mt-2 px-3 py-1 text-xs text-slate-600 hover:text-red-700 rounded border border-slate-200">
            Sign Out
          </button>
        </div>
      </aside>

      {/* Main Container */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top Bar */}
        <header className="h-16 bg-white border-b border-slate-200 px-4 md:px-8 flex items-center justify-between sticky top-0 z-30 shadow-xs">
          <div className="flex items-center gap-3">
            <button
              type="button"
              className="md:hidden p-2 text-slate-600 hover:bg-slate-100 rounded-lg focus:outline-hidden focus:ring-2 focus:ring-indigo-500"
              onClick={() => setMobileOpen(!mobileOpen)}
              aria-label="Toggle navigation"
              aria-expanded={mobileOpen}
              aria-controls="sidebar-nav"
            >
              ☰
            </button>
            <h1 className="text-base md:text-lg font-semibold text-slate-900 tracking-tight">
              {pageTitle}
            </h1>
          </div>

          <div className="flex items-center gap-3">
            <span className="hidden sm:inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium bg-slate-100 text-slate-700 border border-slate-200">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" aria-hidden="true" />
              Region: {region}
            </span>
            <span className="text-xs text-slate-600 hidden md:inline">{user?.email}</span>
            <button type="button" onClick={() => signOut()} className="text-xs text-slate-500 hover:text-red-600 px-2 py-1 rounded hover:bg-slate-100">
              Sign Out
            </button>
          </div>
        </header>

        {/* Workspace Content */}
        <main id="app-workspace" className="flex-1 p-4 md:p-8 max-w-7xl w-full mx-auto">
          {allowed ? children : (
            <div className="p-8 max-w-lg mx-auto bg-white rounded-xl border border-red-200 text-center space-y-2">
              <h2 className="text-base font-semibold text-slate-900">Access Restricted</h2>
              <p className="text-xs text-slate-600">HR Administrator privileges required. Backend authorization boundaries are enforced.</p>
              <Link href="/chat" className="inline-block px-3 py-1.5 bg-indigo-600 text-white text-xs font-medium rounded-lg">Return to Employee Chat</Link>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
