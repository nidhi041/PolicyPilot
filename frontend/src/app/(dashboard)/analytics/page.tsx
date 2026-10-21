import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "HR Analytics — PolicyPilot",
  description: "Monitor employee question trends, policy resolution rates, and knowledge gaps.",
};

export default function AnalyticsPage() {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-xs">
      <h2 className="text-xl font-bold text-slate-900 tracking-tight">HR Analytics</h2>
      <p className="mt-1 text-sm text-slate-500">
        Gain actionable insights into recurring questions, employee feedback, and policy clarity gaps.
      </p>
    </div>
  );
}
