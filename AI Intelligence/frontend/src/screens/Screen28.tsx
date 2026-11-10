import React, { useState } from 'react';
import { AuthenticatedLayout, Card } from '../components/shared';
import { apiErrorMessage, userFacingMessage } from '../lib/api';
import { askResearchQuestion } from '../services/aiService';
import type { RagCitation } from '../services/aiService';

type Answer = { role: 'user' | 'ai'; content: string; citations?: RagCitation[] };

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
        content: data.answer || userFacingMessage(data.message, 'The assistant could not complete that request. Please try again.'),
        citations: data.citations || [],
      }]);
    } catch (error) {
      setMessages((prev) => [...prev, { role: 'ai', content: apiErrorMessage(error, 'The assistant is unavailable right now. Please try again.') }]);
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
                {message.role === 'ai' && message.citations?.length ? (
                  <div className="mt-4 border-t border-slate-200 pt-3">
                    <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Sources</p>
                    <div className="space-y-2 text-xs text-slate-500">
                      {message.citations.map((citation, citationIndex) => (
                        <div key={citationIndex}>
                          <span className="font-medium">{citation.backend_thesis_id}</span>
                          {citation.page_number != null ? ` · page ${citation.page_number}` : ''}
                          {citation.relevance_score != null ? ` · score ${Number(citation.relevance_score).toFixed(2)}` : ''}
                          {citation.text_snippet ? <div className="mt-1 text-slate-600">{citation.text_snippet.slice(0, 200)}</div> : null}
                        </div>
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
