import React, { useState } from 'react';
import { AuthenticatedLayout } from '../components/shared';
import { askResearchQuestion } from '../services/aiService';

type Message = { role: 'user' | 'ai'; content: string };

const Screen27AIAssistant = () => {
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);

  const handleSend = async () => {
    const question = input.trim();
    if (!question || loading) return;
    setInput('');
    setMessages((prev) => [...prev, { role: 'user', content: question }]);
    setLoading(true);
    try {
      const data = await askResearchQuestion(question);
      setMessages((prev) => [...prev, { role: 'ai', content: data.answer || data.message || 'No answer returned.' }]);
    } catch (error) {
      setMessages((prev) => [...prev, { role: 'ai', content: error instanceof Error ? error.message : 'AI request failed.' }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthenticatedLayout title="AI Research Assistant">
      <div className="mx-auto flex h-[600px] max-w-4xl flex-col">
        <div className="flex-1 overflow-y-auto rounded-lg border border-slate-200 bg-slate-50 p-5">
          {messages.length === 0 && <p className="text-sm text-slate-500">Ask a question about the indexed OAU research corpus.</p>}
          {messages.map((message, index) => (
            <div key={index} className={`mb-4 ${message.role === 'user' ? 'text-right' : 'text-left'}`}>
              <div className={`inline-block max-w-[85%] rounded-lg px-4 py-3 text-sm ${message.role === 'user' ? 'bg-[#00502F] text-white' : 'border border-slate-200 bg-white text-slate-800'}`}>
                <div className="whitespace-pre-wrap">{message.content}</div>
              </div>
            </div>
          ))}
          {loading && <p className="text-sm italic text-slate-500">AI is retrieving evidence…</p>}
        </div>
        <div className="mt-3 flex gap-2">
          <input value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') void handleSend(); }} className="flex-1 rounded-md border border-slate-300 p-3" placeholder="Ask a research question…" />
          <button onClick={() => void handleSend()} disabled={loading || !input.trim()} className="rounded-md bg-[#00502F] px-5 py-3 font-semibold text-white disabled:opacity-50">Send</button>
        </div>
      </div>
    </AuthenticatedLayout>
  );
};

export default Screen27AIAssistant;
