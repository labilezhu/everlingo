import { useCallback, useEffect, useRef, useState } from 'react';
import { NotebookPen, User } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import MessageBubble from './MessageBubble';
import ChatInput from './ChatInput';
import TaskSelector from './TaskSelector';
import { Button } from '@/components/ui/button';
import { createSession, sendMessage, connectSSE, buildEnvelope, type ConnStatus } from '@/services/sseClient';
import { loadChatState, saveChatState, clearChatState } from '@/services/chatStorage';
import type { TaskKind, SSEEvent, ResourceContext } from '@/types/chat';
import { Message, uid } from '@/types/chat';
import { LinkListenerContext } from './MarkdownRenderer';

function decodeBase64Audio(b64: string): string {
  const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
  return URL.createObjectURL(new Blob([bytes], { type: 'audio/mpeg' }));
}

export default function ChatWindow({ embedded, linkListener, resourceContextProvider }: {
  embedded?: boolean;
  linkListener?: (url: string) => boolean;
  resourceContextProvider?: () => ResourceContext[];
}) {
  const { t } = useTranslation('chatbot');
  const [initialState] = useState(() => loadChatState());
  const [sessionId, setSessionId] = useState<string | null>(initialState?.sessionId ?? null);
  const [messages, setMessages] = useState<Message[]>(
    initialState && initialState.messages.length > 0
      ? initialState.messages
      : [{ id: uid(), text: t('welcome_text'), from: 'bot' }],
  );
  const [task, setTask] = useState<TaskKind>('none');
  const [thinking, setThinking] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [connStatus, setConnStatus] = useState<ConnStatus | null>(null);
  const [sessionEpoch, setSessionEpoch] = useState(0);
  const retryNowRef = useRef<(() => void) | null>(null);
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
    if (sessionId) {
      saveChatState({ sessionId, messages });
    }
  }, [sessionId, messages]);

  // 连接 effect — 依赖 sessionEpoch，可被手动或 session_expired 触发重建
  useEffect(() => {
    let cleanup: (() => void) | undefined;
    (async () => {
      try {
        let sid = sessionId;
        if (!sid) {
          sid = await createSession();
          setSessionId(sid);
        }
        const conn = connectSSE(
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
          (s: ConnStatus) => { setConnStatus(s); },
        );
        cleanup = conn.cleanup;
        retryNowRef.current = conn.retryNow;
      } catch { setError(t('connect_failed')); }
    })();
    return () => {
      cleanup?.();
      audioRef.current?.pause();
    };
  }, [sessionEpoch]);

  // ref: docs/impl-spec/web-chatbot.md §会话状态持久化 — session 过期（SSE 404）时
  // 走「手动重启」：显示提示条，用户点「重新开始」才清 sessionStorage + 新建 session。
  // 不自动清空，否则页面卸载/导航期间 EventSource 误触发 onerror 会把存储清掉，
  // 导致跨页跳转回来后无法复用 session。
  const handleRebuild = useCallback(() => {
    clearChatState();
    setConnStatus(null);
    setSessionId(null);
    setMessages(prev => [...prev, { id: uid(), text: t('session_reset_note'), from: 'system' }]);
    setSessionEpoch(prev => prev + 1);
  }, [t]);

  const handleSend = useCallback(async (text: string) => {
    if (!sessionId) return;
    setMessages(prev => [...prev, { id: uid(), text, from: 'user' }]);
    setPending(true);
    try {
      const extraContexts = resourceContextProvider?.() ?? [];
      const envelope = buildEnvelope(task, text, extraContexts);
      await sendMessage(sessionId, envelope);
    } catch {
      setPending(false);
      setError(t('send_failed'));
    }
  }, [sessionId, task, resourceContextProvider, t]);

  return (
    <LinkListenerContext.Provider value={linkListener}>
    <div className={'flex flex-col h-full px-0 md:px-6 border-x-0 md:border-x border-border' + (embedded ? ' chat-embedded' : '')}>
      <header className="flex items-center justify-between gap-2 px-3 py-2 md:px-4 md:py-3 border-b border-border bg-background">
        <div className="flex items-center gap-2">
          <span className="text-xl">🐹</span>
          <h1 className="text-lg font-semibold text-foreground">{t('app_name')}</h1>
        </div>
        {!embedded && (
          <div className="flex items-center gap-1">
            <Button variant="ghost" size="sm" onClick={() => { window.location.href = '/editor'; }}>
              <NotebookPen />
              <span className="hidden md:inline">{t('notes')}</span>
            </Button>
            <Button variant="ghost" size="sm" onClick={() => { window.location.href = '/console/me'; }}>
              <User />
              <span className="hidden md:inline">{t('me')}</span>
            </Button>
          </div>
        )}
      </header>

      <TaskSelector task={task} onChange={setTask} />

      {error && (
        <div className="px-4 py-2 bg-red-50 text-red-600 text-sm border-b border-red-200">
          {error}
        </div>
      )}

      {connStatus?.state === 'reconnecting' && (
        <div className="px-4 py-2 bg-amber-50 text-amber-700 text-sm border-b border-amber-200 flex items-center justify-between gap-2">
          <span>{t('reconnecting', { count: connStatus.countdown })}</span>
          <button
            onClick={() => retryNowRef.current?.()}
            className="underline whitespace-nowrap font-medium shrink-0"
          >
            {t('retry_now')}
          </button>
        </div>
      )}

      {connStatus?.state === 'session_expired' && (
        <div className="px-4 py-2 bg-amber-50 text-amber-700 text-sm border-b border-amber-200 flex items-center justify-between gap-2">
          <span>{t('session_expired')}</span>
          <button
            onClick={handleRebuild}
            className="underline whitespace-nowrap font-medium shrink-0"
          >
            {t('restart')}
          </button>
        </div>
      )}

      <div className="flex-1 overflow-y-auto overscroll-contain px-3 py-3 md:px-4 md:py-4 space-y-4">
        {messages.map(msg => (
          <MessageBubble key={msg.id} message={msg} onReplay={playAudio} />
        ))}

        {thinking && (
          <div className="flex justify-start">
            <div className="bg-muted text-foreground rounded-2xl rounded-bl-md px-4 py-2 animate-pulse">
              {t('thinking')}
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      <ChatInput onSend={handleSend} disabled={!sessionId} pending={pending} />
    </div>
    </LinkListenerContext.Provider>
  );
}
