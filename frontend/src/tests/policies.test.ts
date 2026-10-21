import test from "node:test";
import assert from "node:assert/strict";
import {
  fetchPolicies,
  uploadPolicy,
  processPolicyVersion,
  reviewPolicyVersion,
  publishPolicyVersion,
  fetchPolicyDetail,
  replacePolicyVersion,
  archivePolicyVersion,
  downloadPolicyPdf,
} from "../lib/policies.ts";

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

test("replacePolicyVersion, archivePolicyVersion, and fetchPolicyDetail handle success and errors", async () => {
  const calls: string[] = [];
  const mockFetch = (async (url: string | URL | Request, init?: RequestInit) => {
    const s = String(url);
    calls.push(`${init?.method || "GET"} ${s}`);
    if (s.includes("unauthorized")) return { ok: false, json: async () => ({ detail: "Forbidden: HR Admin required" }) } as unknown as Response;
    return { ok: true, json: async () => ({ id: "v-2", version_label: "2.0", status: "draft" }) } as unknown as Response;
  }) as typeof fetch;
  const replaced = await replacePolicyVersion("tok", "p-1", new FormData(), mockFetch);
  assert.equal(replaced.version_label, "2.0");
  await archivePolicyVersion("tok", "p-1", "v-1", mockFetch);
  const detail = await fetchPolicyDetail("tok", "p-1", mockFetch);
  assert.equal(detail.id, "v-2");
  assert.match(String(calls[0]), /POST .*\/p-1\/versions/);
  assert.match(String(calls[1]), /POST .*\/p-1\/versions\/v-1\/archive/);
  assert.match(String(calls[2]), /GET .*\/p-1/);
  await assert.rejects(async () => fetchPolicyDetail("bad-tok", "unauthorized", mockFetch), /Forbidden/);
});

test("downloadPolicyPdf fetches blob with authentication and handles errors", async () => {
  const mockFetch = (async (url: string | URL | Request, init?: RequestInit) => {
    const s = String(url);
    assert.match(s, /\/api\/v1\/storage\/policies\/policies\/global\/test\.pdf\/download/);
    assert.equal((init?.headers as Record<string, string>)["Authorization"], "Bearer valid-token");
    return {
      ok: true,
      blob: async () => new Blob(["%PDF-1.4 test"], { type: "application/pdf" }),
    } as unknown as Response;
  }) as typeof fetch;

  const blob = await downloadPolicyPdf("valid-token", "policies/global/test.pdf", mockFetch);
  assert.equal(blob.type, "application/pdf");
  assert.equal(blob.size, 13);

  const failFetch = (async () => ({
    ok: false,
    status: 404,
    json: async () => ({ detail: "File not found in storage" }),
  })) as unknown as typeof fetch;

  await assert.rejects(
    async () => downloadPolicyPdf("valid-token", "missing.pdf", failFetch),
    /File not found in storage/
  );
});

