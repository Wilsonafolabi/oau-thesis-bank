import React, { useEffect, useState } from 'react';
import { Bot, Send, Trash2 } from 'lucide-react';
import { AuthenticatedLayout, Button, useAppRouter } from '../components/shared';
import { apiErrorMessage, userFacingMessage } from '../lib/api';
import { askGeneralAssistant } from '../services/aiService';
import type { AssistantMessage, AssistantModelTier } from '../services/aiService';

const STORAGE_PREFIX = 'oau:assistant:messages';

type Msg = { role: 'user' | 'assistant'; content: string };

const Screen27AIAssistant = () => {
  const { user } = useAppRouter();
  const storageKey = `${STORAGE_PREFIX}:${user?.id ?? 'anon'}`;

  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<Msg[]>(() => {
    try {
      const raw = sessionStorage.getItem(storageKey);
      return raw ? JSON.parse(raw) : [];
    } catch {
      return [];
    }
  });
  const [provider, setProvider] = useState<AssistantModelTier>('model-1');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    try {
      sessionStorage.setItem(storageKey, JSON.stringify(messages));
    } catch {
      // storage may be unavailable; ignore
    }
  }, [messages, storageKey]);

  const handleSend = async () => {
    const question = input.trim();
    if (!question || loading) return;
    const next: Msg[] = [...messages, { role: 'user', content: question }];
    setMessages(next);
    setInput('');
    setLoading(true);
    try {
      const history: AssistantMessage[] = next.map((m) => ({ role: m.role, content: m.content }));
      const data = await askGeneralAssistant(history, provider);
      setMessages((prev) => [...prev, { role: 'assistant', content: data.answer || userFacingMessage(data.message, 'The assistant could not complete that request. Please try again.') }]);
    } catch (error) {
      setMessages((prev) => [...prev, { role: 'assistant', content: apiErrorMessage(error, 'The assistant is unavailable right now. Please try again.') }]);
    } finally {
      setLoading(false);
    }
  };

  const clearChat = () => {
    setMessages([]);
    try {
      sessionStorage.removeItem(storageKey);
    } catch {
      // ignore
    }
  };

  return (
    <AuthenticatedLayout title="AI Research Assistant">
      <div className="mx-auto max-w-5xl px-4 py-6 sm:px-6 lg:py-8">
        <section className="mx-auto flex h-[min(720px,calc(100vh-12rem))] min-h-[480px] max-w-4xl flex-col overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
          <header className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-200 px-4 py-4 sm:px-6">
            <div className="flex min-w-0 items-center gap-3">
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-emerald-50 text-emerald-800">
                <Bot className="h-5 w-5" aria-hidden="true" />
              </span>
              <div className="min-w-0">
                <h2 className="truncate text-sm font-semibold text-slate-900">OAU Research Assistant</h2>
                <p className="mt-0.5 text-xs text-slate-500">General knowledge · not thesis-cited</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <label className="text-xs font-medium text-slate-500" htmlFor="assistant-provider">Model</label>
              <select
                id="assistant-provider"
                value={provider}
                onChange={(event) => setProvider(event.target.value as AssistantModelTier)}
                className="h-9 rounded-md border border-slate-300 bg-white px-2 text-sm text-slate-700 focus:border-emerald-700 focus:outline-none focus:ring-2 focus:ring-emerald-700/15"
              >
                <option value="model-1">Model 1</option>
                <option value="model-2">Model 2</option>
              </select>
              <button
                type="button"
                onClick={clearChat}
                disabled={messages.length === 0 || loading}
                aria-label="Clear conversation"
                title="Clear conversation"
                className="flex h-9 w-9 items-center justify-center rounded-md text-slate-500 transition hover:bg-slate-100 hover:text-slate-900 disabled:cursor-not-allowed disabled:opacity-40"
              >
                <Trash2 className="h-4 w-4" aria-hidden="true" />
              </button>
            </div>
          </header>

          <div className="flex-1 space-y-5 overflow-y-auto bg-slate-50/60 px-4 py-5 sm:px-6" role="log" aria-live="polite" aria-relevant="additions text">
            {messages.length === 0 ? (
              <div className="flex h-full min-h-64 flex-col items-center justify-center px-4 text-center">
                <span className="flex h-12 w-12 items-center justify-center rounded-full bg-white text-emerald-800 shadow-sm ring-1 ring-slate-200">
                  <Bot className="h-6 w-6" aria-hidden="true" />
                </span>
                <h3 className="mt-4 text-lg font-semibold text-slate-900">How can I help with your research?</h3>
                <p className="mt-2 max-w-md text-sm leading-6 text-slate-500">
                  Ask a question to start a conversation. For answers grounded in indexed theses with citations, use AI Answer With Sources.
                </p>
              </div>
            ) : (
              messages.map((message, index) => (
                <div key={`${message.role}-${index}`} className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div className={`max-w-[90%] whitespace-pre-wrap rounded-lg px-4 py-3 text-sm leading-6 sm:max-w-[80%] ${message.role === 'user' ? 'bg-[#00502F] text-white' : 'border border-slate-200 bg-white text-slate-800'}`}>
                    {message.content}
                  </div>
                </div>
              ))
            )}
            {loading && <p className="text-sm italic text-slate-500" role="status">Thinking…</p>}
          </div>

          <form
            className="border-t border-slate-200 bg-white p-3 sm:p-4"
            onSubmit={(event) => {
              event.preventDefault();
              void handleSend();
            }}
          >
            <label className="sr-only" htmlFor="assistant-message">Message</label>
            <div className="flex items-end gap-2 rounded-lg border border-slate-300 bg-white p-2 focus-within:border-emerald-700 focus-within:ring-2 focus-within:ring-emerald-700/15">
              <textarea
                id="assistant-message"
                rows={2}
                value={input}
                onChange={(event) => setInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' && !event.shiftKey) {
                    event.preventDefault();
                    void handleSend();
                  }
                }}
                className="max-h-36 min-h-12 flex-1 resize-y border-0 bg-transparent px-2 py-1.5 text-sm text-slate-900 outline-none placeholder:text-slate-400"
                placeholder="Ask a research question…"
              />
              <Button
                type="submit"
                disabled={loading || !input.trim()}
                className="h-10 w-10 shrink-0 px-0"
                aria-label="Send message"
              >
                <Send className="h-4 w-4" aria-hidden="true" />
              </Button>
            </div>
            <p className="mt-2 px-1 text-[11px] text-slate-400">General knowledge responses may need independent verification.</p>
          </form>
        </section>
      </div>
    </AuthenticatedLayout>
  );
};

export default Screen27AIAssistant;
