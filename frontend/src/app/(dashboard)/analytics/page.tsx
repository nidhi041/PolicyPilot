"use client";

import React, { useState, useEffect } from "react";
import { useAuth } from "@/context/AuthContext";
import { fetchAnalyticsOverview, type HRAnalyticsOverview } from "@/lib/analytics";

export default function AnalyticsPage() {
  const { session, profile, isLoading: authLoading } = useAuth();
  const [data, setData] = useState<HRAnalyticsOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [region, setRegion] = useState("ALL");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [reloadKey, setReloadKey] = useState(0);

  const isHr = Boolean(profile?.is_hr_administrator);
  const userRegion = profile?.region || "GLOBAL";

  useEffect(() => {
    let active = true;
    (async () => {
      await Promise.resolve();
      if (!active || !session?.access_token || !isHr) return;
      setLoading(true); setError(null);
      try {
        const res = await fetchAnalyticsOverview(session.access_token, {
          region: userRegion !== "GLOBAL" ? userRegion : region,
          start_date: startDate ? `${startDate}T00:00:00Z` : undefined,
          end_date: endDate ? `${endDate}T23:59:59Z` : undefined,
        });
        if (active) setData(res);
      } catch (err) {
        if (active) setError(err instanceof Error ? err.message : "Failed to load HR analytics");
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => { active = false; };
  }, [session, isHr, userRegion, region, startDate, endDate, reloadKey]);

  if (authLoading) return <div className="p-8 text-center text-slate-500">Checking permissions...</div>;
  if (!isHr) return (
    <div className="rounded-xl border border-rose-200 bg-rose-50/50 p-6 text-center text-rose-800">
      <h3 className="text-base font-semibold">Access Restricted</h3>
      <p className="mt-1 text-sm text-rose-600">HR Administrator credentials are required to view organization analytics.</p>
    </div>
  );

  const maxDaily = Math.max(...(data?.question_volume.daily_trend.map((d) => d.questions_count) || [1]), 1);
  const kpis = data ? [
    { label: "Total Questions", val: data.question_volume.total_questions, sub: `${data.question_volume.total_conversations} conversations`, col: "text-slate-900" },
    { label: "Grounded Rate", val: `${data.answer_outcomes.grounded_rate}%`, sub: `${data.answer_outcomes.grounded_answers_count} grounded / ${data.answer_outcomes.abstention_count} abstentions`, col: "text-emerald-600" },
    { label: "Satisfaction Rate", val: `${data.feedback_summary.satisfaction_rate}%`, sub: `👍 ${data.feedback_summary.positive_feedback_count} · 👎 ${data.feedback_summary.negative_feedback_count} (${data.feedback_summary.response_rate}% rate)`, col: "text-indigo-600" },
    { label: "Confirmed Resolved", val: data.answer_outcomes.confirmed_resolved_count, sub: `${data.answer_outcomes.confirmed_unresolved_count} unverified / flagged`, col: "text-slate-900" },
  ] : [];

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between rounded-xl border border-slate-200 bg-white p-5 shadow-xs">
        <div>
          <h2 className="text-xl font-bold tracking-tight text-slate-900">HR Analytics & Intelligence</h2>
          <p className="text-sm text-slate-500">Employee query trends, resolution metrics, and policy clarity gaps</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {userRegion === "GLOBAL" ? (
            <select aria-label="Filter by region" value={region} onChange={(e) => setRegion(e.target.value)} className="rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs text-slate-700">
              <option value="ALL">All Regions</option><option value="US">US</option><option value="EU">EU</option><option value="APAC">APAC</option>
            </select>
          ) : <span className="rounded-md bg-indigo-50 px-2 py-1 text-xs font-semibold text-indigo-700 border border-indigo-200">Region: {userRegion}</span>}
          <input type="date" aria-label="Start date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className="rounded-lg border border-slate-300 bg-white px-2 py-1 text-xs text-slate-700" />
          <input type="date" aria-label="End date" value={endDate} onChange={(e) => setEndDate(e.target.value)} className="rounded-lg border border-slate-300 bg-white px-2 py-1 text-xs text-slate-700" />
          {(startDate || endDate || region !== "ALL") && (
            <button onClick={() => { setStartDate(""); setEndDate(""); setRegion("ALL"); }} className="text-xs text-slate-500 hover:text-slate-800 underline">Reset</button>
          )}
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800 flex justify-between items-center">
          <span>{error}</span><button onClick={() => setReloadKey((k) => k + 1)} className="font-semibold underline">Retry</button>
        </div>
      )}

      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 animate-pulse">{[1, 2, 3, 4].map((i) => <div key={i} className="h-28 rounded-xl bg-slate-200" />)}</div>
      ) : !data || data.question_volume.total_questions === 0 ? (
        <div className="rounded-xl border border-slate-200 bg-white p-12 text-center shadow-xs">
          <div className="mx-auto w-12 h-12 rounded-full bg-slate-100 flex items-center justify-center text-xl text-slate-400">📊</div>
          <h3 className="mt-3 text-base font-semibold text-slate-800">No Analytics Activity</h3>
          <p className="mt-1 text-sm text-slate-500 max-w-sm mx-auto">No employee questions or feedback recorded in this region and date range. Employee chat interactions will appear here in real time.</p>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {kpis.map((k) => (
              <div key={k.label} className="rounded-xl border border-slate-200 bg-white p-5 shadow-xs">
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">{k.label}</span>
                <div className={`mt-2 text-2xl font-bold ${k.col}`}>{k.val}</div>
                <p className="mt-1 text-xs text-slate-500">{k.sub}</p>
              </div>
            ))}
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2 rounded-xl border border-slate-200 bg-white p-5 shadow-xs">
              <h3 className="text-sm font-semibold text-slate-900 mb-4">Daily Question Volume Trend</h3>
              {data.question_volume.daily_trend.length === 0 ? (
                <div className="h-44 flex items-center justify-center text-xs text-slate-400">No trend entries in date range</div>
              ) : (
                <div className="h-48 flex items-end gap-2 pt-6 pb-2 border-b border-slate-100 overflow-x-auto">
                  {data.question_volume.daily_trend.map((d) => (
                    <div key={d.date} className="flex-1 flex flex-col items-center min-w-8 group">
                      <span className="text-[10px] text-slate-500 mb-1 opacity-0 group-hover:opacity-100 transition-opacity font-medium">{d.questions_count}</span>
                      <div style={{ height: `${Math.max(Math.round((d.questions_count / maxDaily) * 100), 8)}%` }} className="w-full max-w-10 rounded-t bg-indigo-500 hover:bg-indigo-600 transition-all" />
                      <span className="text-[10px] text-slate-500 mt-2 whitespace-nowrap">{d.date.slice(5)}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-xs">
              <h3 className="text-sm font-semibold text-slate-900 mb-4">Answer Outcome Distribution</h3>
              <div className="space-y-4">
                <div>
                  <div className="flex justify-between text-xs font-medium text-slate-700 mb-1">
                    <span>Grounded ({data.answer_outcomes.grounded_answers_count})</span>
                    <span>{data.answer_outcomes.grounded_rate}%</span>
                  </div>
                  <div className="w-full bg-slate-100 rounded-full h-2"><div className="bg-emerald-500 h-2 rounded-full" style={{ width: `${data.answer_outcomes.grounded_rate}%` }} /></div>
                </div>
                <div>
                  <div className="flex justify-between text-xs font-medium text-slate-700 mb-1">
                    <span>Abstentions ({data.answer_outcomes.abstention_count})</span>
                    <span>{data.answer_outcomes.abstention_rate}%</span>
                  </div>
                  <div className="w-full bg-slate-100 rounded-full h-2"><div className="bg-amber-500 h-2 rounded-full" style={{ width: `${data.answer_outcomes.abstention_rate}%` }} /></div>
                </div>
                <div className="pt-4 border-t border-slate-100 text-xs text-slate-500 space-y-1">
                  <p>• Confirmed resolved requires explicit positive feedback.</p>
                  <p>• Abstentions trigger when grounding score is insufficient.</p>
                </div>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-xs">
              <h3 className="text-sm font-semibold text-slate-900 mb-3">Popular Policy Topics</h3>
              {data.popular_topics.length === 0 ? (
                <p className="text-xs text-slate-400 py-6 text-center">No policy citations recorded yet.</p>
              ) : (
                <div className="space-y-3">
                  {data.popular_topics.map((t) => (
                    <div key={t.category}>
                      <div className="flex justify-between text-xs font-medium text-slate-700 mb-1">
                        <span>{t.category}</span>
                        <span className="text-slate-500">{t.count} ({t.percentage}%)</span>
                      </div>
                      <div className="w-full bg-slate-100 rounded-full h-2"><div className="bg-indigo-500 h-2 rounded-full" style={{ width: `${t.percentage}%` }} /></div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-xs">
              <h3 className="text-sm font-semibold text-slate-900 mb-3">Unanswered & Low-Confidence Queries</h3>
              {data.unanswered_questions.length === 0 ? (
                <p className="text-xs text-slate-400 py-6 text-center">No unanswered or flagged queries in this period.</p>
              ) : (
                <div className="divide-y divide-slate-100 max-h-64 overflow-y-auto">
                  {data.unanswered_questions.map((q, idx) => (
                    <div key={idx} className="py-2.5 flex items-start justify-between gap-3 text-xs">
                      <div className="flex-1">
                        <p className="font-medium text-slate-800 line-clamp-2">{q.question}</p>
                        <span className="text-[10px] text-slate-400">Last asked: {q.last_asked.slice(0, 10)}</span>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold text-slate-600">{q.count}x</span>
                        <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${q.outcome === "negative_feedback" ? "bg-rose-50 text-rose-700 border border-rose-200" : "bg-amber-50 text-amber-700 border border-amber-200"}`}>
                          {q.outcome === "negative_feedback" ? "Downvoted" : "Abstention"}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
