import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Policy Management — PolicyPilot",
  description: "Upload, review, publish, and manage company policies and versions.",
};

export default function PoliciesPage() {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-xs">
      <h2 className="text-xl font-bold text-slate-900 tracking-tight">Policy Management</h2>
      <p className="mt-1 text-sm text-slate-500">
        Review, publish, and manage policy documents, regional compliance, and historical versions.
      </p>
    </div>
  );
}
