export interface DailyTrendItem { date: string; questions_count: number; }
export interface QuestionVolume { total_questions: number; total_conversations: number; daily_trend: DailyTrendItem[]; }
export interface AnswerOutcomes { total_answers: number; grounded_answers_count: number; abstention_count: number; grounded_rate: number; abstention_rate: number; confirmed_resolved_count: number; confirmed_unresolved_count: number; }
export interface FeedbackSummary { total_feedback_count: number; positive_feedback_count: number; negative_feedback_count: number; satisfaction_rate: number; response_rate: number; }
export interface TopicMetric { category: string; count: number; percentage: number; }
export interface UnansweredQuestionItem { question: string; count: number; last_asked: string; outcome: string; }
export interface AnalyticsFilterSummary { region?: string | null; start_date?: string | null; end_date?: string | null; }
export interface HRAnalyticsOverview {
  filters: AnalyticsFilterSummary; question_volume: QuestionVolume; answer_outcomes: AnswerOutcomes;
  feedback_summary: FeedbackSummary; popular_topics: TopicMetric[]; unanswered_questions: UnansweredQuestionItem[];
}
export interface AnalyticsFilterParams { region?: string; start_date?: string; end_date?: string; }

const getBaseUrl = () => process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export async function fetchAnalyticsOverview(token: string, filters: AnalyticsFilterParams = {}, fetchFn = fetch): Promise<HRAnalyticsOverview> {
  const p = new URLSearchParams();
  if (filters.region && filters.region !== "ALL") p.set("region", filters.region);
  if (filters.start_date?.trim()) p.set("start_date", filters.start_date.trim());
  if (filters.end_date?.trim()) p.set("end_date", filters.end_date.trim());
  const res = await fetchFn(`${getBaseUrl()}/api/v1/analytics/overview${p.toString() ? `?${p.toString()}` : ""}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "Failed to load HR analytics");
  return res.json();
}
