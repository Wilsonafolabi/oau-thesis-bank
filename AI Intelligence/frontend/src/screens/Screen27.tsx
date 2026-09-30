import React, { useState } from 'react';
import { AuthenticatedLayout } from '../components/shared';

const Screen27AIAssistant = () => {
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<{role: string, content: string}[]>([]);
  const [loading, setLoading] = useState(false);

  const handleSend = async () => {
    if (!input.trim()) return;
    setLoading(true);
    setMessages(prev => [...prev, { role: 'user', content: input }]);

    try {
      const response = await fetch('http://localhost:8000/api/ai/rag-query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: input })
      });
      const data = await response.json();
      setMessages(prev => [...prev, { role: 'ai', content: data.answer || JSON.stringify(data) }]);
    } catch (error) {
      setMessages(prev => [...prev, { role: 'ai', content: 'Error connecting to AI.' }]);
    } finally {
      setLoading(false);
      setInput('');
    }
  };

  return (
    <AuthenticatedLayout title="AI Research Assistant">
      <div style={{ padding: '20px', maxWidth: '800px', margin: '0 auto' }}>
        <div style={{ height: '400px', overflowY: 'auto', border: '1px solid #ccc', padding: '10px', marginBottom: '10px', borderRadius: '8px', background: '#f9f9f9' }}>
          {messages.map((msg, i) => (
            <div key={i} style={{ marginBottom: '10px', textAlign: msg.role === 'user' ? 'right' : 'left' }}>
              <strong>{msg.role === 'user' ? 'You: ' : 'AI: '}</strong>
              <div style={{ display: 'inline-block', padding: '8px 12px', borderRadius: '8px', background: msg.role === 'user' ? '#007bff' : '#e9ecef', color: msg.role === 'user' ? 'white' : 'black', whiteSpace: 'pre-wrap', maxWidth: '80%' }}>
                {msg.content}
              </div>
            </div>
          ))}
          {loading && <div style={{ fontStyle: 'italic', color: '#666' }}>AI is thinking...</div>}
        </div>
        <div style={{ display: 'flex', gap: '10px' }}>
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSend()}
            placeholder="Ask a research question..."
            style={{ flex: 1, padding: '10px', borderRadius: '4px', border: '1px solid #ccc' }}
          />
          <button onClick={handleSend} disabled={loading} style={{ padding: '10px 20px', borderRadius: '4px', border: 'none', background: '#007bff', color: 'white', cursor: 'pointer' }}>
            Send
          </button>
        </div>
      </div>
    </AuthenticatedLayout>
  );
};

export default Screen27AIAssistant;