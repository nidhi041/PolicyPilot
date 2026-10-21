"use client";

import React, { useState, useRef, useEffect } from "react";
import { useAuth } from "@/context/AuthContext";
import {
  sendChatMessage,
  fetchConversations,
  fetchConversation,
  type ChatMessage,
  type ConversationSummary,
} from "@/lib/chat";

export default function ChatPage() {
  const { session } = useAuth();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conversationId, setConversationId] = useState<string | undefined>();
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<Record<string, "up" | "down">>({});
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const refreshHistory = async () => {
    if (!session?.access_token) return;
    setLoadingHistory(true);
    setHistoryError(null);
    try { setConversations(await fetchConversations(session.access_token)); }
    catch { setHistoryError("Unable to load history"); }
    finally { setLoadingHistory(false); }
  };

  useEffect(() => {
    let active = true;
    (async () => {
      await Promise.resolve();
      if (!active || !session?.access_token) return;
      setLoadingHistory(true);
      try { const c = await fetchConversations(session.access_token); if (active) setConversations(c); }
      catch { if (active) setHistoryError("Unable to load history"); }
      finally { if (active) setLoadingHistory(false); }
    })();
    return () => { active = false; };
  }, [session]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isSubmitting]);

  const selectConversation = async (id: string) => {
    if (!session?.access_token || isSubmitting) return;
    setError(null);
    try {
      const detail = await fetchConversation(session.access_token, id);
      setConversationId(id);
      setMessages(detail.messages.map((m) => ({ id: m.id, role: m.role, content: m.content, status: m.status, citations: m.citations, isGrounded: m.is_grounded })));
    } catch {
      setError("Failed to load conversation");
    }
  };

  const handleNewChat = () => { setConversationId(undefined); setMessages([]); setError(null); };

  const handleSubmit = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const clean = input.trim();
    if (!clean || isSubmitting) return;

    setError(null);
    const userMsg: ChatMessage = { id: `u-${Date.now()}`, role: "user", content: clean };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setIsSubmitting(true);

    try {
      const token = session?.access_token || "";
      const resp = await sendChatMessage(token, clean, conversationId);
      setConversationId(resp.conversation_id);
      const botMsg: ChatMessage = {
        id: `a-${Date.now()}`,
        role: "assistant",
        content: resp.answer,
        status: resp.status,
        citations: resp.citations,
        isGrounded: resp.is_grounded,
      };
      setMessages((prev) => [...prev, botMsg]);
      refreshHistory();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to retrieve policy answer");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)] max-w-4xl mx-auto bg-white rounded-xl border border-slate-200 shadow-xs overflow-hidden">
      {/* Conversation History Bar */}
      <div className="px-4 py-2 border-b border-slate-200 bg-slate-50 flex items-center justify-between gap-2 overflow-x-auto text-xs shrink-0">
        <div className="flex items-center gap-2 overflow-x-auto">
          <span className="font-semibold text-slate-500 uppercase tracking-wider shrink-0">History:</span>
          {loadingHistory ? <span className="text-slate-400">Loading history...</span> : historyError ? (
            <span className="text-red-500">{historyError} <button type="button" onClick={refreshHistory} className="underline">Retry</button></span>
          ) : conversations.length === 0 ? <span className="text-slate-400">No previous chats</span> : (
            conversations.map((c) => (
              <button
                key={c.id}
                type="button"
                onClick={() => selectConversation(c.id)}
                className={`px-2 py-1 rounded truncate max-w-[130px] transition-colors ${conversationId === c.id ? "bg-indigo-600 text-white font-medium" : "bg-white border border-slate-200 text-slate-700 hover:bg-slate-100"}`}
              >
                {c.title}
              </button>
            ))
          )}
        </div>
        <button type="button" onClick={handleNewChat} className="px-2.5 py-1 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 font-medium rounded shrink-0">
          + New Chat
        </button>
      </div>

      {/* Messages Thread */}
      <div className="flex-1 p-4 md:p-6 overflow-y-auto space-y-4">
        {messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-center p-6 space-y-3 text-slate-500">
            <div className="w-12 h-12 rounded-full bg-indigo-50 text-indigo-600 flex items-center justify-center text-xl font-bold">
              💬
            </div>
            <h2 className="text-lg font-semibold text-slate-800">PolicyPilot Assistant</h2>
            <p className="text-sm max-w-md">
              Ask natural language questions about parental leave, expenses, remote work, or benefits. Every answer is grounded in verified company policy.
            </p>
          </div>
        ) : (
          messages.map((msg) => (
            <div key={msg.id} className={`flex flex-col ${msg.role === "user" ? "items-end" : "items-start"}`}>
              <div
                className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm shadow-xs ${
                  msg.role === "user" ? "bg-indigo-600 text-white rounded-br-xs" : "bg-slate-50 border border-slate-200 text-slate-900 rounded-bl-xs"
                }`}
              >
                {/* Status Badges */}
                {msg.role === "assistant" && (
                  <div className="flex items-center gap-2 mb-2">
                    {msg.status === "abstention" ? (
                      <span className="inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full bg-amber-100 text-amber-800">
                        ⚠ Policy Abstention
                      </span>
                    ) : msg.isGrounded ? (
                      <span className="inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800">
                        ✓ Grounded Answer
                      </span>
                    ) : null}
                  </div>
                )}

                <p className="whitespace-pre-wrap leading-relaxed">{msg.content}</p>

                {/* Citations List */}
                {msg.citations && msg.citations.length > 0 && (
                  <div className="mt-3 pt-3 border-t border-slate-200/80 space-y-1.5" aria-label="Policy Citations">
                    <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Verified Sources:</p>
                    <div className="flex flex-wrap gap-2">
                      {msg.citations.map((c, idx) => (
                        <div key={idx} className="bg-white border border-slate-200 rounded-lg px-2.5 py-1 text-xs text-slate-700 shadow-2xs">
                          <span className="font-medium text-indigo-700">{c.policy_title}</span>
                          <span className="text-slate-400 mx-1">·</span>
                          <span className="text-slate-500">v{c.version} (p. {c.page_number})</span>
                          {c.quote && <p className="italic text-slate-500 mt-0.5 line-clamp-2">&quot;{c.quote}&quot;</p>}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Feedback Controls for Assistant */}
              {msg.role === "assistant" && (
                <div className="flex items-center gap-2 mt-1 px-1 text-xs text-slate-400">
                  {feedback[msg.id] ? (
                    <span className="text-emerald-600 font-medium">Thank you for your feedback!</span>
                  ) : (
                    <>
                      <span>Was this helpful?</span>
                      <button
                        type="button"
                        onClick={() => setFeedback((f) => ({ ...f, [msg.id]: "up" }))}
                        className="hover:text-slate-700 px-1 rounded"
                        aria-label="Mark helpful"
                      >
                        👍
                      </button>
                      <button
                        type="button"
                        onClick={() => setFeedback((f) => ({ ...f, [msg.id]: "down" }))}
                        className="hover:text-slate-700 px-1 rounded"
                        aria-label="Mark unhelpful"
                      >
                        👎
                      </button>
                    </>
                  )}
                </div>
              )}
            </div>
          ))
        )}

        {/* Loading Indicator */}
        {isSubmitting && (
          <div className="flex items-center gap-2 text-slate-500 text-xs py-2 px-3 bg-slate-50 border border-slate-200 rounded-xl w-fit animate-pulse">
            <span className="w-2 h-2 rounded-full bg-indigo-600 animate-ping" />
            <span>Searching policy documents and verifying citations...</span>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Error Banner */}
      {error && (
        <div role="alert" className="mx-4 mb-2 p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700 flex justify-between items-center">
          <span>{error}</span>
          <button type="button" onClick={() => setError(null)} className="text-red-500 hover:text-red-800 font-bold ml-2">✕</button>
        </div>
      )}

      {/* Input Bar */}
      <form onSubmit={handleSubmit} className="p-3 bg-slate-50 border-t border-slate-200 flex gap-2 items-center">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={isSubmitting}
          placeholder="Ask a question about company policy..."
          aria-label="Ask a policy question"
          className="flex-1 px-4 py-2.5 text-sm bg-white border border-slate-300 rounded-lg focus:outline-hidden focus:ring-2 focus:ring-indigo-500 disabled:bg-slate-100"
        />
        <button
          type="submit"
          disabled={!input.trim() || isSubmitting}
          className="px-4 py-2.5 bg-indigo-600 hover:bg-indigo-700 disabled:bg-slate-300 text-white text-sm font-semibold rounded-lg shadow-xs transition-colors flex items-center gap-1.5"
        >
          <span>Send</span>
          <span aria-hidden="true">➤</span>
        </button>
      </form>
    </div>
  );
}
