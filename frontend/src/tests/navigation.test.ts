import test from "node:test";
import assert from "node:assert/strict";
import { NAV_ITEMS, getPageTitle } from "../components/nav-config.ts";

test("navigation includes required employee chat, policy management, and HR analytics routes", () => {
  const routes = NAV_ITEMS.map((item) => item.href);
  assert.ok(routes.includes("/chat"), "Expected /chat route");
  assert.ok(routes.includes("/policies"), "Expected /policies route");
  assert.ok(routes.includes("/analytics"), "Expected /analytics route");
  assert.strictEqual(NAV_ITEMS.length, 3);
});

test("navigation items have accessible non-empty labels and icons", () => {
  for (const item of NAV_ITEMS) {
    assert.ok(item.label.length > 0, `Item with href ${item.href} has empty label`);
    assert.ok(item.icon.length > 0, `Item with href ${item.href} has empty icon`);
    assert.ok(item.href.startsWith("/"), `Item href ${item.href} must be absolute path`);
  }
});

test("getPageTitle correctly identifies active route titles and enterprise fallback", () => {
  assert.strictEqual(getPageTitle("/chat"), "Employee Chat");
  assert.strictEqual(getPageTitle("/chat/session-123"), "Employee Chat");
  assert.strictEqual(getPageTitle("/policies"), "Policy Management");
  assert.strictEqual(getPageTitle("/policies/upload"), "Policy Management");
  assert.strictEqual(getPageTitle("/analytics"), "HR Analytics");
  assert.strictEqual(getPageTitle("/"), "PolicyPilot Enterprise");
  assert.strictEqual(getPageTitle("/unknown"), "PolicyPilot Enterprise");
});
