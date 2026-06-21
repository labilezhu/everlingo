import { useCallback, useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { createSession, sendMessage, connectSSE } from './sse';
import type { SSEEvent } from './sse';

interface Message {
  id: string;
  text: string;
  from: 'user' | 'bot';
}

function uid() { return Math.random().toString(36).slice(2, 10); }

export default function ChatBot() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([
    { id: uid(), text: '你好！我是小记🐹，你的 AI 外语老师。有什么可以帮你的吗？', from: 'bot' },
  ]);
  const [input, setInput] = useState('');
  const [thinking, setThinking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages, thinking]);

  useEffect(() => {
    let cleanup: (() => void) | undefined;
    (async () => {
      try {
        const sid = await createSession();
        setSessionId(sid);
        cleanup = connectSSE(
          sid,
          (e: SSEEvent) => {
            if (e.type === 'message') {
              setMessages(prev => [...prev, { id: uid(), text: (e.data as { text: string }).text, from: 'bot' }]);
              setThinking(false);
            } else {
              setThinking((e.data as { typing: boolean }).typing);
            }
          },
          () => setError('连接断开，请刷新页面重试'),
        );
      } catch { setError('无法连接到服务器'); }
    })();
    return () => cleanup?.();
  }, []);

  async function handleSend(e: React.FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text || !sessionId) return;
    setInput('');
    setMessages(prev => [...prev, { id: uid(), text, from: 'user' }]);
    try { await sendMessage(sessionId, text); } catch { setError('发送消息失败'); }
  }

  return (
    <div className="flex flex-col h-screen max-w-2xl mx-auto border-x border-[var(--border)]">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-[var(--border)] bg-[var(--bg-primary)]">
        <span className="text-xl">🐹</span>
        <h1 className="text-lg font-semibold text-[var(--text-primary)]">小记</h1>
      </div>

      {error && (
        <div className="px-4 py-2 bg-red-50 text-red-600 text-sm border-b border-red-200">{error}</div>
      )}

      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {messages.map(msg => (
          <div key={msg.id} className={`flex ${msg.from === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[80%] rounded-2xl px-4 py-2 ${
              msg.from === 'user'
                ? 'bg-[var(--accent)] text-white rounded-br-md'
                : 'bg-[var(--bg-secondary)] text-[var(--text-primary)] rounded-bl-md'
            }`}>
              <div className="prose prose-sm max-w-none">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.text}</ReactMarkdown>
              </div>
            </div>
          </div>
        ))}

        {thinking && (
          <div className="flex justify-start">
            <div className="bg-[var(--bg-secondary)] rounded-2xl rounded-bl-md px-4 py-3 flex gap-1">
              <span className="w-2 h-2 bg-[var(--text-secondary)] rounded-full animate-bounce [animation-delay:0ms]" />
              <span className="w-2 h-2 bg-[var(--text-secondary)] rounded-full animate-bounce [animation-delay:150ms]" />
              <span className="w-2 h-2 bg-[var(--text-secondary)] rounded-full animate-bounce [animation-delay:300ms]" />
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      <form onSubmit={handleSend} className="flex items-center gap-2 border-t border-[var(--border)] px-4 py-3">
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          placeholder="输入单词、句子或提问..."
          className="flex-1 rounded-full border border-[var(--border)] px-4 py-2 text-sm outline-none focus:border-[var(--accent)] transition-colors"
          disabled={!sessionId}
        />
        <button
          type="submit"
          disabled={!input.trim() || !sessionId}
          className="rounded-full bg-[var(--accent)] text-white px-4 py-2 text-sm font-medium disabled:opacity-40 hover:opacity-90 transition-opacity"
        >
          发送
        </button>
      </form>
    </div>
  );
}
