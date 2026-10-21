import test from "node:test";
import assert from "node:assert/strict";
import {
  sendChatMessage,
  fetchConversations,
  fetchConversation,
  type ChatResponse,
} from "../lib/chat.ts";

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

test("fetchConversations and fetchConversation retrieve user-scoped history", async () => {
  const mockList = [{ id: "c-1", title: "Leave Inquiry", created_at: "2026-10-19T00:00:00Z", updated_at: "2026-10-19T00:00:00Z" }];
  const mockDetail = { id: "c-1", title: "Leave Inquiry", messages: [{ id: "m-1", role: "user", content: "Leave days?" }] };

  const mockFetch = (async (url: string | URL | Request) => {
    const s = String(url);
    if (s.endsWith("/conversations/c-1")) return { ok: true, json: async () => mockDetail } as unknown as Response;
    if (s.endsWith("/conversations")) return { ok: true, json: async () => mockList } as unknown as Response;
    return { ok: false, status: 404 } as unknown as Response;
  }) as typeof fetch;

  const list = await fetchConversations("tok", mockFetch);
  assert.equal(list.length, 1);
  assert.equal(list[0]?.title, "Leave Inquiry");

  const detail = await fetchConversation("tok", "c-1", mockFetch);
  assert.equal(detail.id, "c-1");
  assert.equal(detail.messages.length, 1);
});
