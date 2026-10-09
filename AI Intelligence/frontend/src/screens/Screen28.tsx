import React, { useState } from 'react';
import { AuthenticatedLayout, Card } from '../components/shared';
import { askResearchQuestion } from '../services/aiService';

type Answer = { role: 'user' | 'ai'; content: string; sources?: Array<{ document_id: string; page: number; similarity: number }> };

const Screen28AIAnswer = () => {
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<Answer[]>([]);
  const [loading, setLoading] = useState(false);

  const handleSend = async () => {
    const question = input.trim();
    if (!question || loading) return;
    setInput('');
    setMessages((prev) => [...prev, { role: 'user', content: question }]);
    setLoading(true);
    try {
      const data = await askResearchQuestion(question);
      setMessages((prev) => [...prev, {
        role: 'ai',
        content: data.answer || data.message || 'No answer returned.',
        sources: data.sources || [],
      }]);
    } catch (error) {
      setMessages((prev) => [...prev, { role: 'ai', content: error instanceof Error ? error.message : 'AI request failed.' }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthenticatedLayout title="AI Answer With Sources">
      <div className="mx-auto flex h-[600px] max-w-4xl flex-col">
        <div className="flex-1 space-y-4 overflow-y-auto">
          {messages.map((message, index) => (
            <div key={index} className={message.role === 'user' ? 'text-right' : 'text-left'}>
              <Card className={`inline-block max-w-[90%] p-4 text-left ${message.role === 'user' ? 'bg-[#00502F] text-white' : ''}`}>
                <div className="whitespace-pre-wrap">{message.content}</div>
                {message.role === 'ai' && message.sources?.length ? (
                  <div className="mt-4 border-t border-slate-200 pt-3">
                    <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Sources</p>
                    <div className="space-y-1 text-xs text-slate-500">
                      {message.sources.map((source, sourceIndex) => (
                        <div key={sourceIndex}>Document {source.document_id} · page {source.page} · similarity {Number(source.similarity).toFixed(3)}</div>
                      ))}
                    </div>
                  </div>
                ) : null}
              </Card>
            </div>
          ))}
          {loading && <p className="text-sm italic text-slate-500">Retrieving and grounding answer…</p>}
        </div>
        <div className="mt-3 flex gap-2">
          <input value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') void handleSend(); }} className="flex-1 rounded-md border border-slate-300 p-3" placeholder="Ask a research question…" />
          <button onClick={() => void handleSend()} disabled={loading || !input.trim()} className="rounded-md bg-[#00502F] px-5 py-3 font-semibold text-white disabled:opacity-50">Ask</button>
        </div>
      </div>
    </AuthenticatedLayout>
  );
};

export default Screen28AIAnswer;
