import test from "node:test";
import assert from "node:assert/strict";
import { sendChatMessage, type ChatResponse } from "../lib/chat.ts";

test("sendChatMessage rejects empty questions", async () => {
  await assert.rejects(async () => sendChatMessage("token", "   "), /Question cannot be empty/);
});

test("sendChatMessage retrieves grounded answer with citations", async () => {
  const mockResp: ChatResponse = {
    conversation_id: "conv-1",
    status: "answered",
    answer: "16 weeks paid parental leave.",
    citations: [{ policy_title: "Leave Policy", version: "1.0", page_number: 2, quote: "16 weeks" }],
    is_grounded: true,
    confidence: "high",
  };
  const mockFetch = (async (url: string | URL | Request, init?: RequestInit) => {
    assert.match(String(url), /\/api\/v1\/chat/);
    const headers = init?.headers as Record<string, string>;
    assert.equal(headers["Authorization"], "Bearer jwt");
    assert.equal(JSON.parse(String(init?.body)).message, "leave?");
    return { ok: true, json: async () => mockResp } as unknown as Response;
  }) as typeof fetch;

  const res = await sendChatMessage("jwt", "leave?", undefined, mockFetch);
  assert.equal(res.status, "answered");
  assert.equal(res.is_grounded, true);
  assert.equal(res.citations.length, 1);
  assert.equal(res.citations[0]?.policy_title, "Leave Policy");
});

test("sendChatMessage handles abstention response", async () => {
  const mockResp: ChatResponse = {
    conversation_id: "conv-2",
    status: "abstention",
    answer: "Unable to answer: Insufficient evidence.",
    citations: [],
    is_grounded: false,
    confidence: "abstain",
  };
  const mockFetch = (async () => ({ ok: true, json: async () => mockResp })) as unknown as typeof fetch;
  const res = await sendChatMessage("tok", "alien leave?", undefined, mockFetch);
  assert.equal(res.status, "abstention");
  assert.equal(res.is_grounded, false);
});

test("sendChatMessage propagates API error messages", async () => {
  const mockFetch = (async () => ({
    ok: false,
    status: 400,
    json: async () => ({ detail: "Invalid policy" }),
  })) as unknown as typeof fetch;
  await assert.rejects(async () => sendChatMessage("tok", "msg", undefined, mockFetch), /Invalid policy/);
});
