import { useCallback, useEffect, useRef, useState } from 'react';
import MessageBubble from './MessageBubble';
import ChatInput from './ChatInput';
import { createSession, sendMessage, connectSSE } from '@/services/sseClient';
import type { SSEEvent } from '@/types/chat';
import { Message, uid } from '@/types/chat';

export default function ChatWindow() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([
    { id: uid(), text: '你好！我是小记🐹，你的 AI 外语老师。有什么可以帮你的吗？', from: 'bot' },
  ]);
  const [thinking, setThinking] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, thinking]);

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
              setPending(false);
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

  const handleSend = useCallback(async (text: string) => {
    if (!sessionId) return;
    setMessages(prev => [...prev, { id: uid(), text, from: 'user' }]);
    setPending(true);
    try {
      await sendMessage(sessionId, text);
    } catch {
      setPending(false);
      setError('发送消息失败');
    }
  }, [sessionId]);

  return (
    <div className="flex flex-col h-screen px-6 border-x border-border">
      <header className="flex items-center gap-2 px-4 py-3 border-b border-border bg-background">
        <span className="text-xl">🐹</span>
        <h1 className="text-lg font-semibold text-foreground">小记</h1>
      </header>

      {error && (
        <div className="px-4 py-2 bg-red-50 text-red-600 text-sm border-b border-red-200">
          {error}
        </div>
      )}

      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {messages.map(msg => (
          <MessageBubble key={msg.id} message={msg} />
        ))}

        {thinking && (
          <div className="flex justify-start">
            <div className="bg-muted text-foreground rounded-2xl rounded-bl-md px-4 py-2 animate-pulse">
              小记🐹正在思考……
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      <ChatInput onSend={handleSend} disabled={!sessionId} pending={pending} />
    </div>
  );
}
