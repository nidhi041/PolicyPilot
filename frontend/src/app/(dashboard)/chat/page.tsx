import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Employee Policy Chat — PolicyPilot",
  description: "Ask policy questions and receive verified, citation-backed answers.",
};

export default function ChatPage() {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-xs">
      <h2 className="text-xl font-bold text-slate-900 tracking-tight">Employee Policy Chat</h2>
      <p className="mt-1 text-sm text-slate-500">
        Ask natural language questions about your company policies with region-aware retrieval and citations.
      </p>
    </div>
  );
}
