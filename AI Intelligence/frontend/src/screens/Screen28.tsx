import React, { useState } from 'react';
import { AuthenticatedLayout } from '../components/shared';

const Screen28AIAnswer = () => {
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);

  const handleSend = async () => {
    if (!input.trim()) return;
    setLoading(true);
    setMessages(prev => [...prev, { role: 'user', content: input }]);
    try {
      const res = await fetch('http://localhost:8000/api/ai/rag-query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: input })
      });
      const data = await res.json();
      setMessages(prev => [...prev, { role: 'ai', content: data.answer || JSON.stringify(data) }]);
    } catch (e) { setMessages(prev => [...prev, { role: 'ai', content: 'Error connecting.' }]); }
    setLoading(false);
    setInput('');
  };

  return (
    <AuthenticatedLayout title="AI Research Assistant">
      <div className="p-6 max-w-3xl mx-auto flex flex-col h-[600px]">
        <div className="flex-1 overflow-y-auto border rounded p-4 mb-4 bg-gray-50">
          {messages.map((msg, i) => (
            <div key={i} className={`mb-3 ${msg.role === 'user' ? 'text-right' : 'text-left'}`}>
              <div className={`inline-block p-3 rounded-lg ${msg.role === 'user' ? 'bg-green-600 text-white' : 'bg-white border'}`}>
                {msg.content}
              </div>
            </div>
          ))}
          {loading && <div className="text-gray-500 italic">AI is thinking...</div>}
        </div>
        <div className="flex gap-2">
          <input value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && handleSend()} className="flex-1 p-3 border rounded" placeholder="Ask a research question..." />
          <button onClick={handleSend} disabled={loading} className="bg-green-600 text-white px-6 py-3 rounded hover:bg-green-700 disabled:opacity-50">Send</button>
        </div>
      </div>
    </AuthenticatedLayout>
  );
};
export default Screen28AIAnswer;