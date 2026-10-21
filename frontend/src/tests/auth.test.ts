import test from "node:test";
import assert from "node:assert/strict";
import { isSessionExpired, type AuthSession } from "../lib/auth.ts";
import { canAccessRoute, getVisibleNavItems } from "../components/nav-config.ts";

test("unauthenticated navigation is denied for all dashboard routes", () => {
  assert.equal(canAccessRoute("/chat", false, false), false);
  assert.equal(canAccessRoute("/policies", false, false), false);
  assert.equal(canAccessRoute("/analytics", false, false), false);
});

test("session expiration distinguishes active vs expired sessions", () => {
  assert.equal(isSessionExpired(null), true);
  const expired: AuthSession = { access_token: "t", expires_at: Math.floor(Date.now() / 1000) - 10, user: { id: "1", email: "a@b.com" } };
  assert.equal(isSessionExpired(expired), true);
  const active: AuthSession = { access_token: "t", expires_at: Math.floor(Date.now() / 1000) + 3600, user: { id: "1", email: "a@b.com" } };
  assert.equal(isSessionExpired(active), false);
});

test("role-specific navigation filters HR-only routes for employees", () => {
  const emp = getVisibleNavItems(false);
  assert.equal(emp.length, 1);
  assert.equal(emp[0]?.href, "/chat");
  const hr = getVisibleNavItems(true);
  assert.equal(hr.length, 3);
  assert.deepEqual(hr.map((i) => i.href), ["/chat", "/policies", "/analytics"]);
});

test("HR-only route authorization guard protects sensitive routes", () => {
  assert.equal(canAccessRoute("/policies", true, false), false);
  assert.equal(canAccessRoute("/analytics", true, false), false);
  assert.equal(canAccessRoute("/policies", true, true), true);
  assert.equal(canAccessRoute("/analytics", true, true), true);
});
