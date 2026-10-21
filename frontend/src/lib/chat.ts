export interface Citation { policy_title: string; version: string; page_number: number; quote?: string | null; }
export interface ChatResponse { conversation_id: string; message_id?: string; status: string; answer: string; citations: Citation[]; is_grounded: boolean; confidence: string; }
export interface ChatMessage { id: string; role: "user" | "assistant"; content: string; status?: string; citations?: Citation[]; isGrounded?: boolean; feedback?: "up" | "down" | null; }
export interface ConversationSummary { id: string; title: string; created_at: string; updated_at: string; }
export interface ConversationDetail { id: string; title: string; messages: { id: string; role: "user" | "assistant"; content: string; status?: string; citations?: Citation[]; is_grounded?: boolean; feedback?: "up" | "down" | null; }[]; }
export interface FeedbackResponse { id: string; message_id: string; user_id: string; rating: "up" | "down"; created_at: string; updated_at: string; }

export async function sendChatMessage(token: string, message: string, conversationId?: string, fetchFn = fetch): Promise<ChatResponse> {
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

export async function fetchConversations(token: string, fetchFn = fetch): Promise<ConversationSummary[]> {
  const base = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
  const res = await fetchFn(`${base}/api/v1/conversations`, { headers: { Authorization: `Bearer ${token}` } });
  if (!res.ok) throw new Error("Failed to load conversations");
  return res.json();
}

export async function fetchConversation(token: string, id: string, fetchFn = fetch): Promise<ConversationDetail> {
  const base = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
  const res = await fetchFn(`${base}/api/v1/conversations/${id}`, { headers: { Authorization: `Bearer ${token}` } });
  if (!res.ok) throw new Error("Failed to load conversation");
  return res.json();
}

export async function submitMessageFeedback(
  token: string,
  messageId: string,
  rating: "up" | "down",
  fetchFn = fetch
): Promise<FeedbackResponse> {
  const base = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
  const res = await fetchFn(`${base}/api/v1/chat/messages/${messageId}/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ rating }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || err.message || `Feedback submission failed (${res.status})`);
  }
  return res.json();
}
