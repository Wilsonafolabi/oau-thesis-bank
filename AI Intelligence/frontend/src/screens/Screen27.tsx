import React, { useEffect, useState } from 'react';
import { AuthenticatedLayout, useAppRouter } from '../components/shared';
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
      setMessages((prev) => [...prev, { role: 'assistant', content: data.answer || data.message || 'No answer returned.' }]);
    } catch (error) {
      setMessages((prev) => [...prev, { role: 'assistant', content: error instanceof Error ? error.message : 'AI request failed.' }]);
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
      <div className="mx-auto flex h-[600px] max-w-4xl flex-col">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <p className="text-xs text-slate-500">
            General-knowledge assistant. For cited answers from the thesis corpus, use “AI Answer With Sources”.
          </p>
          <div className="flex items-center gap-2">
            <label className="text-xs text-slate-500" htmlFor="assistant-provider">Model</label>
            <select
              id="assistant-provider"
              value={provider}
              onChange={(e) => setProvider(e.target.value as AssistantModelTier)}
              className="rounded-md border border-slate-300 px-2 py-1 text-xs"
            >
              <option value="model-1">Model 1</option>
              <option value="model-2">Model 2</option>
            </select>
            <button onClick={clearChat} className="rounded-md border border-slate-300 px-3 py-1 text-xs text-slate-600">Clear</button>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto rounded-lg border border-slate-200 bg-slate-50 p-5">
          {messages.length === 0 && <p className="text-sm text-slate-500">Ask anything — this assistant answers from general knowledge.</p>}
          {messages.map((message, index) => (
            <div key={index} className={`mb-4 ${message.role === 'user' ? 'text-right' : 'text-left'}`}>
              <div className={`inline-block max-w-[85%] whitespace-pre-wrap rounded-lg px-4 py-3 text-sm ${message.role === 'user' ? 'bg-[#00502F] text-white' : 'border border-slate-200 bg-white text-slate-800'}`}>
                {message.content}
              </div>
            </div>
          ))}
          {loading && <p className="text-sm italic text-slate-500">Thinking…</p>}
        </div>
        <div className="mt-3 flex gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') void handleSend(); }}
            className="flex-1 rounded-md border border-slate-300 p-3"
            placeholder="Ask anything…"
          />
          <button
            onClick={() => void handleSend()}
            disabled={loading || !input.trim()}
            className="rounded-md bg-[#00502F] px-5 py-3 font-semibold text-white disabled:opacity-50"
          >
            Send
          </button>
        </div>
      </div>
    </AuthenticatedLayout>
  );
};

export default Screen27AIAssistant;
