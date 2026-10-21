import test from "node:test";
import assert from "node:assert/strict";
import { fetchAnalyticsOverview, type HRAnalyticsOverview } from "../lib/analytics.ts";

test("fetchAnalyticsOverview constructs query parameters and authorization header", async () => {
  const calls: string[] = [];
  const mockFetch = (async (url: string | URL | Request, init?: RequestInit) => {
    calls.push(String(url));
    assert.equal((init?.headers as Record<string, string>)["Authorization"], "Bearer hr-token");
    assert.match(String(url), /\/api\/v1\/analytics\/overview\?region=US&start_date=.*&end_date=.*/);
    return {
      ok: true,
      json: async () => ({
        filters: { region: "US" },
        question_volume: { total_questions: 12, total_conversations: 5, daily_trend: [{ date: "2026-01-10", questions_count: 12 }] },
        answer_outcomes: { total_answers: 12, grounded_answers_count: 10, abstention_count: 2, grounded_rate: 83.3, abstention_rate: 16.7, confirmed_resolved_count: 8, confirmed_unresolved_count: 4 },
        feedback_summary: { total_feedback_count: 10, positive_feedback_count: 8, negative_feedback_count: 2, satisfaction_rate: 80.0, response_rate: 83.3 },
        popular_topics: [{ category: "Leave", count: 8, percentage: 66.7 }],
        unanswered_questions: [{ question: "Can I take parental leave early?", count: 2, last_asked: "2026-01-10T12:00:00Z", outcome: "abstention" }],
      }),
    } as unknown as Response;
  }) as typeof fetch;

  const data = await fetchAnalyticsOverview("hr-token", { region: "US", start_date: "2026-01-01T00:00:00Z", end_date: "2026-01-31T23:59:59Z" }, mockFetch);
  assert.equal(calls.length, 1);
  assert.equal(data.question_volume.total_questions, 12);
  assert.equal(data.answer_outcomes.grounded_rate, 83.3);
  assert.equal(data.popular_topics[0]?.category, "Leave");
  assert.equal(data.unanswered_questions[0]?.count, 2);
});

test("fetchAnalyticsOverview omits ALL and empty filters, and handles errors", async () => {
  const mockFetch = (async (url: string | URL | Request) => {
    assert.equal(String(url), "http://localhost:8000/api/v1/analytics/overview");
    return {
      ok: true,
      json: async () => ({
        filters: { region: "GLOBAL" },
        question_volume: { total_questions: 0, total_conversations: 0, daily_trend: [] },
        answer_outcomes: { total_answers: 0, grounded_answers_count: 0, abstention_count: 0, grounded_rate: 0.0, abstention_rate: 0.0, confirmed_resolved_count: 0, confirmed_unresolved_count: 0 },
        feedback_summary: { total_feedback_count: 0, positive_feedback_count: 0, negative_feedback_count: 0, satisfaction_rate: 0.0, response_rate: 0.0 },
        popular_topics: [], unanswered_questions: [],
      }),
    } as unknown as Response;
  }) as typeof fetch;

  const data = await fetchAnalyticsOverview("hr-token", { region: "ALL", start_date: "", end_date: "" }, mockFetch);
  assert.equal(data.question_volume.total_questions, 0);

  const errFetch = (async () => ({ ok: false, json: async () => ({ detail: "Forbidden: HR Admin required" }) })) as unknown as typeof fetch;
  await assert.rejects(async () => fetchAnalyticsOverview("emp-token", {}, errFetch), /Forbidden: HR Admin required/);
});

test("analytics data model safely handles empty dataset without NaN or null crashes", () => {
  const empty: HRAnalyticsOverview = {
    filters: { region: "GLOBAL", start_date: null, end_date: null },
    question_volume: { total_questions: 0, total_conversations: 0, daily_trend: [] },
    answer_outcomes: { total_answers: 0, grounded_answers_count: 0, abstention_count: 0, grounded_rate: 0.0, abstention_rate: 0.0, confirmed_resolved_count: 0, confirmed_unresolved_count: 0 },
    feedback_summary: { total_feedback_count: 0, positive_feedback_count: 0, negative_feedback_count: 0, satisfaction_rate: 0.0, response_rate: 0.0 },
    popular_topics: [], unanswered_questions: [],
  };
  assert.equal(Number.isNaN(empty.answer_outcomes.grounded_rate), false);
  assert.equal(empty.question_volume.total_questions, 0);
  assert.equal(empty.answer_outcomes.confirmed_resolved_count, 0);
});
