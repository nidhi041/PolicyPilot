export interface Citation { policy_title: string; version: string; page_number: number; quote?: string | null; }
export interface ChatResponse { conversation_id: string; status: string; answer: string; citations: Citation[]; is_grounded: boolean; confidence: string; }
export interface ChatMessage { id: string; role: "user" | "assistant"; content: string; status?: string; citations?: Citation[]; isGrounded?: boolean; }

export async function sendChatMessage(
  token: string,
  message: string,
  conversationId?: string,
  fetchFn = fetch,
): Promise<ChatResponse> {
  const clean = message.trim();
  if (!clean) throw new Error("Question cannot be empty");
  const base = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
  const res = await fetchFn(`${base}/api/v1/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ message: clean, ...(conversationId ? { conversation_id: conversationId } : {}) }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || err.message || `Chat request failed (${res.status})`);
  }
  return res.json();
}
