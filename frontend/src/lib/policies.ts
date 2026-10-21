export interface PolicyVersion {
  id: string; policy_id: string; version_label: string;
  status: "draft" | "under_review" | "published" | "archived";
  processing_status: "pending" | "processing" | "completed" | "failed";
  processing_error?: string | null; effective_from?: string | null; effective_to?: string | null; created_at?: string | null;
}
export interface Policy {
  id: string; title: string; category: string; region: string;
  created_at?: string | null; updated_at?: string | null; versions?: PolicyVersion[]; version?: PolicyVersion;
}
export interface PolicyFilterParams { search?: string; region?: string; category?: string; status?: string; }
const getBaseUrl = () => process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export async function fetchPolicies(token: string, filters: PolicyFilterParams = {}, fetchFn = fetch): Promise<Policy[]> {
  const p = new URLSearchParams();
  if (filters.search?.trim()) p.set("search", filters.search.trim());
  if (filters.region && filters.region !== "ALL") p.set("region", filters.region);
  if (filters.category && filters.category !== "ALL") p.set("category", filters.category);
  const res = await fetchFn(`${getBaseUrl()}/api/v1/policies${p.toString() ? `?${p.toString()}` : ""}`, { headers: { Authorization: `Bearer ${token}` } });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "Failed to load policies");
  return res.json();
}
export async function uploadPolicy(token: string, form: FormData, fetchFn = fetch): Promise<Policy> {
  const res = await fetchFn(`${getBaseUrl()}/api/v1/policies`, { method: "POST", headers: { Authorization: `Bearer ${token}` }, body: form });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "Failed to upload policy");
  return res.json();
}
export async function processPolicyVersion(token: string, pid: string, vid: string, fetchFn = fetch): Promise<{ status: string }> {
  const res = await fetchFn(`${getBaseUrl()}/api/v1/policies/${pid}/versions/${vid}/process`, { method: "POST", headers: { Authorization: `Bearer ${token}` } });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "Failed to process policy version");
  return res.json();
}
export async function reviewPolicyVersion(token: string, pid: string, vid: string, status = "under_review", fetchFn = fetch): Promise<PolicyVersion> {
  const res = await fetchFn(`${getBaseUrl()}/api/v1/policies/${pid}/versions/${vid}/review`, { method: "POST", headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" }, body: JSON.stringify({ status }) });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "Failed to update review status");
  return res.json();
}
export async function publishPolicyVersion(token: string, pid: string, vid: string, payload?: { effective_from?: string; effective_to?: string }, fetchFn = fetch): Promise<PolicyVersion> {
  const res = await fetchFn(`${getBaseUrl()}/api/v1/policies/${pid}/versions/${vid}/publish`, { method: "POST", headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" }, body: JSON.stringify(payload || {}) });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "Failed to publish policy version");
  return res.json();
}
export async function fetchPolicyDetail(token: string, pid: string, fetchFn = fetch): Promise<Policy> {
  const res = await fetchFn(`${getBaseUrl()}/api/v1/policies/${pid}`, { headers: { Authorization: `Bearer ${token}` } });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "Failed to load policy detail");
  return res.json();
}
export async function replacePolicyVersion(token: string, pid: string, form: FormData, fetchFn = fetch): Promise<PolicyVersion> {
  const res = await fetchFn(`${getBaseUrl()}/api/v1/policies/${pid}/versions`, { method: "POST", headers: { Authorization: `Bearer ${token}` }, body: form });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "Failed to replace version");
  return res.json();
}
export async function archivePolicyVersion(token: string, pid: string, vid: string, fetchFn = fetch): Promise<PolicyVersion> {
  const res = await fetchFn(`${getBaseUrl()}/api/v1/policies/${pid}/versions/${vid}/archive`, { method: "POST", headers: { Authorization: `Bearer ${token}` } });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "Failed to archive version");
  return res.json();
}

