import test from "node:test";
import assert from "node:assert/strict";
import { fetchPolicies, uploadPolicy, processPolicyVersion, reviewPolicyVersion, publishPolicyVersion } from "../lib/policies.ts";

test("fetchPolicies constructs query parameters and returns policies", async () => {
  const mockFetch = (async (url: string | URL | Request, init?: RequestInit) => {
    assert.match(String(url), /\/api\/v1\/policies\?.*search=leave.*region=US.*category=Leave/);
    assert.equal((init?.headers as Record<string, string>)["Authorization"], "Bearer test-jwt");
    return { ok: true, json: async () => [{ id: "p-1", title: "Parental Leave" }] } as unknown as Response;
  }) as typeof fetch;
  const res = await fetchPolicies("test-jwt", { search: "leave", region: "US", category: "Leave" }, mockFetch);
  assert.equal(res[0]?.title, "Parental Leave");
});

test("fetchPolicies and uploadPolicy handle errors", async () => {
  const errFetch = (async () => ({ ok: false, json: async () => ({ detail: "API Error" }) })) as unknown as typeof fetch;
  await assert.rejects(async () => fetchPolicies("tok", {}, errFetch), /API Error/);
  await assert.rejects(async () => uploadPolicy("tok", new FormData(), errFetch), /API Error/);
});

test("lifecycle actions call expected endpoints and validate publication", async () => {
  const calls: string[] = [];
  const mockFetch = (async (url: string | URL | Request, init?: RequestInit) => {
    const s = String(url);
    calls.push(`${init?.method} ${s}`);
    if (s.endsWith("/publish") && init?.body && JSON.parse(String(init.body)).effective_from === "bad") {
      return { ok: false, json: async () => ({ detail: "Cannot publish unprocessed policy document" }) } as unknown as Response;
    }
    return { ok: true, json: async () => ({ status: "success" }) } as unknown as Response;
  }) as typeof fetch;
  await processPolicyVersion("tok", "p-1", "v-1", mockFetch);
  await reviewPolicyVersion("tok", "p-1", "v-1", "under_review", mockFetch);
  await publishPolicyVersion("tok", "p-1", "v-1", {}, mockFetch);
  assert.match(String(calls[0]), /POST .*\/p-1\/versions\/v-1\/process/);
  assert.match(String(calls[1]), /POST .*\/p-1\/versions\/v-1\/review/);
  assert.match(String(calls[2]), /POST .*\/p-1\/versions\/v-1\/publish/);
  await assert.rejects(async () => publishPolicyVersion("tok", "p-1", "v-1", { effective_from: "bad" }, mockFetch), /Cannot publish/);
});
