"use client";

import React, { useState, useEffect, useRef } from "react";
import { useAuth } from "@/context/AuthContext";
import {
  fetchPolicies,
  uploadPolicy,
  processPolicyVersion,
  reviewPolicyVersion,
  publishPolicyVersion,
  replacePolicyVersion,
  archivePolicyVersion,
  type Policy,
} from "@/lib/policies";

export default function PoliciesPage() {
  const { session } = useAuth();
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [region, setRegion] = useState("ALL");
  const [category, setCategory] = useState("ALL");
  const [showUpload, setShowUpload] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [replacingId, setReplacingId] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const replaceFileRef = useRef<HTMLInputElement>(null);

  const confirmAction = (msg: string, fn: () => Promise<unknown>, vid: string) => {
    if (typeof window !== "undefined" && !window.confirm(msg)) return;
    return handleAction(fn, vid);
  };

  const loadData = async (tok = session?.access_token) => {
    if (!tok) return;
    setLoading(true);
    setError(null);
    try { setPolicies(await fetchPolicies(tok, { search, region, category })); }
    catch (e) { setError(e instanceof Error ? e.message : "Failed to load policies"); }
    finally { setLoading(false); }
  };

  useEffect(() => {
    let active = true;
    (async () => {
      await Promise.resolve();
      if (!active || !session?.access_token) return;
      setLoading(true);
      try {
        const d = await fetchPolicies(session.access_token, { search, region, category });
        if (active) setPolicies(d);
      } catch (e) { if (active) setError(e instanceof Error ? e.message : "Failed to load policies"); }
      finally { if (active) setLoading(false); }
    })();
    return () => { active = false; };
  }, [session, search, region, category]);

  const handleUpload = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!session?.access_token || uploading) return;
    const form = e.currentTarget;
    if (!fileInputRef.current?.files?.[0]) { setError("Please select a PDF file"); return; }
    setUploading(true);
    setError(null);
    try {
      await uploadPolicy(session.access_token, new FormData(form));
      form.reset();
      setShowUpload(false);
      await loadData();
    } catch (err) { setError(err instanceof Error ? err.message : "Upload failed"); }
    finally { setUploading(false); }
  };

  const handleReplaceVersion = async (e: React.FormEvent<HTMLFormElement>, policyId: string) => {
    e.preventDefault();
    if (!session?.access_token || uploading) return;
    const form = e.currentTarget;
    if (!replaceFileRef.current?.files?.[0]) { setError("Please select a PDF file"); return; }
    setUploading(true);
    setError(null);
    try {
      await replacePolicyVersion(session.access_token, policyId, new FormData(form));
      form.reset();
      setReplacingId(null);
      await loadData();
    } catch (err) { setError(err instanceof Error ? err.message : "Version replacement failed"); }
    finally { setUploading(false); }
  };

  const handleAction = async (action: () => Promise<unknown>, vid: string) => {
    if (!session?.access_token || busyId) return;
    setBusyId(vid);
    setError(null);
    try { await action(); await loadData(); }
    catch (err) { setError(err instanceof Error ? err.message : "Action failed"); }
    finally { setBusyId(null); }
  };

  return (
    <div className="space-y-6 max-w-6xl mx-auto">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold text-slate-900 tracking-tight">Policy Management</h2>
          <p className="text-sm text-slate-500">Upload, review, publish, and manage company policies and compliance versions.</p>
        </div>
        <button type="button" onClick={() => setShowUpload(!showUpload)} className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold shadow-xs">
          {showUpload ? "Cancel" : "+ Upload Policy"}
        </button>
      </div>

      {error && (
        <div className="p-3 bg-red-50 border border-red-200 text-red-700 rounded-lg text-sm flex justify-between items-center">
          <span>{error}</span>
          <button type="button" onClick={() => setError(null)} className="font-bold ml-2">✕</button>
        </div>
      )}

      {showUpload && (
        <form onSubmit={handleUpload} className="p-5 bg-white border border-slate-200 rounded-xl shadow-xs space-y-4">
          <h3 className="text-base font-semibold text-slate-800">Register New Policy Document</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
            <div><label htmlFor="p-t" className="block font-medium mb-1">Title</label><input id="p-t" name="title" required placeholder="e.g. Parental Leave Policy" className="w-full px-3 py-2 border rounded-md" /></div>
            <div><label htmlFor="p-c" className="block font-medium mb-1">Category</label><input id="p-c" name="category" required placeholder="e.g. Leave" className="w-full px-3 py-2 border rounded-md" /></div>
            <div><label htmlFor="p-r" className="block font-medium mb-1">Region Scope</label><select id="p-r" name="region" defaultValue="GLOBAL" className="w-full px-3 py-2 border rounded-md"><option value="GLOBAL">GLOBAL</option><option value="US">US</option><option value="EU">EU</option><option value="APAC">APAC</option></select></div>
            <div><label htmlFor="p-v" className="block font-medium mb-1">Version Label</label><input id="p-v" name="version_label" defaultValue="1.0" required className="w-full px-3 py-2 border rounded-md" /></div>
            <div className="md:col-span-2"><label htmlFor="p-f" className="block font-medium mb-1">PDF File</label><input id="p-f" name="file" type="file" accept=".pdf" ref={fileInputRef} required className="w-full px-3 py-2 border rounded-md" /></div>
          </div>
          <div className="flex justify-end gap-2">
            <button type="button" onClick={() => setShowUpload(false)} className="px-4 py-2 border rounded-md text-sm text-slate-700">Cancel</button>
            <button type="submit" disabled={uploading} className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-md text-sm font-semibold disabled:opacity-50">{uploading ? "Uploading..." : "Save & Register"}</button>
          </div>
        </form>
      )}

      <div className="flex flex-wrap items-center gap-3 p-3 bg-white border border-slate-200 rounded-xl shadow-xs text-sm">
        <input type="text" placeholder="Search policies..." value={search} onChange={(e) => setSearch(e.target.value)} className="px-3 py-1.5 border border-slate-200 rounded-lg w-full sm:w-64" />
        <select value={region} onChange={(e) => setRegion(e.target.value)} className="px-3 py-1.5 border border-slate-200 rounded-lg">
          <option value="ALL">All Regions</option><option value="GLOBAL">GLOBAL</option><option value="US">US</option><option value="EU">EU</option><option value="APAC">APAC</option>
        </select>
        <select value={category} onChange={(e) => setCategory(e.target.value)} className="px-3 py-1.5 border border-slate-200 rounded-lg">
          <option value="ALL">All Categories</option><option value="Leave">Leave</option><option value="Benefits">Benefits</option><option value="Conduct">Conduct</option><option value="Workplace">Workplace</option>
        </select>
      </div>

      <div className="bg-white border border-slate-200 rounded-xl shadow-xs overflow-hidden">
        {loading ? <div className="p-8 text-center text-slate-500 text-sm">Loading policies...</div> : policies.length === 0 ? <div className="p-8 text-center text-slate-500 text-sm">No policies found matching criteria.</div> : (
          <div className="divide-y divide-slate-200">
            {policies.map((p) => {
              const v = p.versions?.[0] || p.version;
              const vers = p.versions || (p.version ? [p.version] : []);
              return (
                <div key={p.id} className="divide-y divide-slate-100">
                  <div className="p-4 sm:p-5 flex flex-col md:flex-row md:items-center justify-between gap-4 hover:bg-slate-50/50">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <h3 className="font-semibold text-slate-900 text-base">{p.title}</h3>
                        <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-slate-100 text-slate-700">{p.category}</span>
                        <span className="px-2 py-0.5 text-xs font-semibold rounded-full bg-indigo-50 text-indigo-700">{p.region}</span>
                      </div>
                      {v && (
                        <div className="flex items-center gap-3 text-xs text-slate-500">
                          <span>Active: <strong className="text-slate-700">v{v.version_label}</strong></span>
                          <span>•</span>
                          <span className={`font-medium ${v.status === "published" ? "text-emerald-600" : v.status === "under_review" ? "text-purple-600" : v.status === "archived" ? "text-slate-400" : "text-slate-600"}`}>Status: {v.status.replace("_", " ").toUpperCase()}</span>
                          <span>•</span>
                          <span className={`font-medium ${v.processing_status === "completed" ? "text-emerald-600" : v.processing_status === "failed" ? "text-red-600" : "text-amber-600"}`}>Processing: {v.processing_status}</span>
                        </div>
                      )}
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <button type="button" onClick={() => setReplacingId(replacingId === p.id ? null : p.id)} className="px-2.5 py-1 text-xs font-medium rounded border border-slate-300 hover:bg-slate-100">
                        {replacingId === p.id ? "Cancel" : "+ New Version"}
                      </button>
                      <button type="button" onClick={() => setExpandedId(expandedId === p.id ? null : p.id)} className="px-2.5 py-1 text-xs font-semibold rounded bg-indigo-50 text-indigo-700 hover:bg-indigo-100">
                        {expandedId === p.id ? "Hide History" : `Inspect Versions (${vers.length})`}
                      </button>
                    </div>
                  </div>

                  {replacingId === p.id && (
                    <form onSubmit={(e) => handleReplaceVersion(e, p.id)} className="p-4 bg-slate-50 flex flex-wrap items-center gap-3 text-xs">
                      <span className="font-semibold text-slate-700">Replace/New Version:</span>
                      <input name="version_label" defaultValue="2.0" required placeholder="Version Label" className="px-2 py-1 border rounded w-28" />
                      <input name="file" type="file" accept=".pdf" ref={replaceFileRef} required className="text-xs" />
                      <button type="submit" disabled={uploading} className="px-3 py-1 bg-indigo-600 text-white font-medium rounded hover:bg-indigo-700 disabled:opacity-50">
                        {uploading ? "Uploading..." : "Upload Version"}
                      </button>
                    </form>
                  )}

                  {expandedId === p.id && (
                    <div className="p-4 bg-slate-50 space-y-2 text-xs">
                      <div className="font-semibold text-slate-700 mb-1">Version History:</div>
                      {vers.map((ver) => {
                        const isBusy = busyId === ver.id;
                        return (
                          <div key={ver.id} className="p-2.5 bg-white border border-slate-200 rounded flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                            <div className="flex items-center gap-2 flex-wrap">
                              <span className="font-bold text-slate-800">v{ver.version_label}</span>
                              <span className={`px-1.5 py-0.5 rounded font-semibold ${ver.status === "published" ? "bg-emerald-100 text-emerald-800" : ver.status === "under_review" ? "bg-purple-100 text-purple-800" : ver.status === "archived" ? "bg-slate-100 text-slate-500" : "bg-slate-100 text-slate-800"}`}>{ver.status.toUpperCase()}</span>
                              <span className={`px-1.5 py-0.5 rounded font-medium ${ver.processing_status === "completed" ? "bg-emerald-50 text-emerald-700" : ver.processing_status === "failed" ? "bg-red-50 text-red-700" : "bg-amber-50 text-amber-700"}`}>Processing: {ver.processing_status}</span>
                            </div>
                            <div className="flex items-center gap-1.5 shrink-0">
                              {ver.processing_status !== "completed" && ver.status !== "archived" && (
                                <button type="button" disabled={isBusy} onClick={() => handleAction(() => processPolicyVersion(session?.access_token || "", p.id, ver.id), ver.id)} className="px-2 py-0.5 rounded bg-amber-50 text-amber-800 hover:bg-amber-100 disabled:opacity-50">{isBusy ? "Processing..." : "Process"}</button>
                              )}
                              {ver.status === "draft" && (
                                <button type="button" disabled={isBusy} onClick={() => handleAction(() => reviewPolicyVersion(session?.access_token || "", p.id, ver.id, "under_review"), ver.id)} className="px-2 py-0.5 rounded bg-purple-50 text-purple-800 hover:bg-purple-100 disabled:opacity-50">Submit Review</button>
                              )}
                              {ver.status !== "published" && ver.status !== "archived" && (
                                <button type="button" disabled={isBusy} onClick={() => confirmAction(`Publish version v${ver.version_label}? This will make it live.`, () => publishPolicyVersion(session?.access_token || "", p.id, ver.id), ver.id)} className="px-2 py-0.5 rounded bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50">Publish</button>
                              )}
                              {ver.status !== "archived" && (
                                <button type="button" disabled={isBusy} onClick={() => confirmAction(`Archive version v${ver.version_label}?`, () => archivePolicyVersion(session?.access_token || "", p.id, ver.id), ver.id)} className="px-2 py-0.5 rounded bg-slate-200 text-slate-700 hover:bg-slate-300 disabled:opacity-50">Archive</button>
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
