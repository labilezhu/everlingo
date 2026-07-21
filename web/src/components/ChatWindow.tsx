import { useCallback, useEffect, useRef, useState } from 'react';
import MessageBubble from './MessageBubble';
import ChatInput from './ChatInput';
import TaskSelector from './TaskSelector';
import { createSession, sendMessage, connectSSE, buildEnvelope } from '@/services/sseClient';
import type { TaskKind, SSEEvent } from '@/types/chat';
import { Message, uid } from '@/types/chat';

function decodeBase64Audio(b64: string): string {
  const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
  return URL.createObjectURL(new Blob([bytes], { type: 'audio/mpeg' }));
}

export default function ChatWindow() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([
    { id: uid(), text: '你好！我是小记🐹，你的 AI 外语老师。有什么可以帮你的吗？', from: 'bot' },
  ]);
  const [task, setTask] = useState<TaskKind>('none');
  const [thinking, setThinking] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  function playAudio(url: string) {
    if (audioRef.current) {
      audioRef.current.pause();
    }
    const audio = new Audio(url);
    audioRef.current = audio;
    audio.play().catch(() => { /* autoplay blocked; user can replay via button */ });
  }

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
            } else if (e.type === 'sound') {
              const { audio } = e.data as { audio: string };
              const url = decodeBase64Audio(audio);
              setMessages(prev => [...prev, { id: uid(), text: '', from: 'bot', audioUrl: url }]);
              playAudio(url);
            } else {
              setThinking((e.data as { typing: boolean }).typing);
            }
          },
          () => setError('连接断开，请刷新页面重试'),
        );
      } catch { setError('无法连接到服务器'); }
    })();
    return () => {
      cleanup?.();
      audioRef.current?.pause();
    };
  }, []);

  const handleSend = useCallback(async (text: string) => {
    if (!sessionId) return;
    setMessages(prev => [...prev, { id: uid(), text, from: 'user' }]);
    setPending(true);
    try {
      const envelope = buildEnvelope(task, text);
      await sendMessage(sessionId, envelope);
    } catch {
      setPending(false);
      setError('发送消息失败');
    }
  }, [sessionId, task]);

  return (
    <div className="flex flex-col h-screen px-6 border-x border-border">
      <header className="flex items-center gap-2 px-4 py-3 border-b border-border bg-background">
        <span className="text-xl">🐹</span>
        <h1 className="text-lg font-semibold text-foreground">小记</h1>
      </header>

      <TaskSelector task={task} onChange={setTask} />

      {error && (
        <div className="px-4 py-2 bg-red-50 text-red-600 text-sm border-b border-red-200">
          {error}
        </div>
      )}

      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {messages.map(msg => (
          <MessageBubble key={msg.id} message={msg} onReplay={playAudio} />
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
