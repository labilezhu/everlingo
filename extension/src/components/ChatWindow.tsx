import { useCallback, useEffect, useRef, useState } from 'react';
import MessageBubble from './MessageBubble';
import ChatInput from './ChatInput';
import TaskSelector from './TaskSelector';
import { connectSSE, sendEnvelope } from '@/services/sseClient';
import { getSession } from '@/services/backgroundClient';
import { loadHistory, appendMessage, clearHistory } from '@/services/messageHistory';
import { buildEnvelope, type TaskKind } from '@/types/envelope';
import type { Message, SSEEvent } from '@/types/chat';
import { uid } from '@/types/chat';

interface PageSnapshot {
  selection: string;
  context: string;
  url: string;
  title: string;
}

export default function ChatWindow() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [task, setTask] = useState<TaskKind>('translate');
  const [messages, setMessages] = useState<Message[]>([
    { id: uid(), text: '你好！我是小记🐹，你的 AI 外语老师。有什么可以帮你的吗？', from: 'bot' },
  ]);
  const [thinking, setThinking] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const snapshotRef = useRef<PageSnapshot>({
    selection: '', context: '', url: '', title: '',
  });
  const sessionIdRef = useRef<string | null>(null);
  const tabIdRef = useRef<number>(0);
  const deviceIdRef = useRef<string>('');

  function playAudio(url: string) {
    if (audioRef.current) {
      audioRef.current.pause();
    }
    const audio = new Audio(url);
    audioRef.current = audio;
    audio.play().catch(() => { /* autoplay blocked */ });
  }

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, thinking]);

  useEffect(() => {
    let cleanup: (() => void) | undefined;
    (async () => {
      try {
        // 读 device_id
        const { device_id } = await chrome.storage.local.get('device_id');
        deviceIdRef.current = device_id || '';

        // 步骤 2a: 查 session（background 返回 sessionId + fresh + tabId）
        const { sessionId: sid, fresh, tabId } = await getSession();
        setSessionId(sid);
        sessionIdRef.current = sid;
        tabIdRef.current = tabId;

        // 步骤 2a: 恢复 UI history
        if (!fresh) {
          const history = await loadHistory(tabId);
          setMessages((prev) => {
            // 保留欢迎消息，后面接历史
            const historyMsgs = history.map((h) => ({
              id: uid(),
              text: h.text,
              from: h.role === 'user' ? 'user' as const : 'bot' as const,
            }));
            return [...prev, ...historyMsgs];
          });
        }

        // 步骤 7: capture snapshot
        const snapshot = await captureSnapshot();
        snapshotRef.current = snapshot;

        // 步骤 8: 连 SSE
        cleanup = connectSSE(sid, (e: SSEEvent) => handleSSEEvent(e, tabId), () => {
          setError('连接断开，请刷新页面重试');
        });

        // 步骤 9: 若 selection 非空，自动发首次请求
        if (snapshot.selection) {
          setPending(true);
          try {
            const env = buildEnvelope(task, '', {
              ...snapshot,
              deviceId: deviceIdRef.current,
            });
            await sendEnvelope(sid, env);
            await appendMessage(tabId, {
              role: 'user',
              text: '',
              timestamp: new Date().toISOString(),
            });
          } catch {
            setPending(false);
          }
        }
      } catch {
        setError('无法连接到服务器');
      }
    })();
    return () => {
      cleanup?.();
      audioRef.current?.pause();
    };
  }, []);

  function handleSSEEvent(e: SSEEvent, tabId: number) {
    if (e.type === 'message') {
      const data = e.data as { text: string; timestamp?: string };
      setMessages((prev) => [
        ...prev,
        { id: uid(), text: data.text, from: 'bot' },
      ]);
      appendMessage(tabId, {
        role: 'assistant',
        text: data.text,
        timestamp: data.timestamp || new Date().toISOString(),
      });
      setPending(false);
      setThinking(false);
    } else if (e.type === 'sound') {
      const { audio } = e.data as { audio: string };
      const bytes = Uint8Array.from(atob(audio), (c) => c.charCodeAt(0));
      const url = URL.createObjectURL(new Blob([bytes], { type: 'audio/mpeg' }));
      setMessages((prev) => [
        ...prev,
        { id: uid(), text: '', from: 'bot', audioUrl: url },
      ]);
      playAudio(url);
    } else {
      setThinking((e.data as { typing: boolean }).typing);
    }
  }

  const handleSend = useCallback(
    async (text: string) => {
      const sid = sessionIdRef.current;
      if (!sid) return;
      const tabId = tabIdRef.current;
      setMessages((prev) => [
        ...prev,
        { id: uid(), text, from: 'user' },
      ]);
      setPending(true);
      const now = new Date().toISOString();
      appendMessage(tabId, { role: 'user', text, timestamp: now });
      try {
        const env = buildEnvelope(task, text, {
          ...snapshotRef.current,
          deviceId: deviceIdRef.current,
        });
        await sendEnvelope(sid, env);
      } catch {
        setPending(false);
        setError('发送消息失败');
      }
    },
    [task],
  );

  return (
    <div className="flex flex-col h-screen border-x border-border bg-background">
      <header className="flex items-center gap-2 px-3 py-2 border-b border-border">
        <span className="text-lg">🐹</span>
        <h1 className="text-base font-semibold text-foreground">小记</h1>
      </header>

      <TaskSelector task={task} onChange={setTask} />

      {error && (
        <div className="px-3 py-1.5 bg-red-50 text-red-600 text-xs border-b border-red-200">
          {error}
        </div>
      )}

      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-3">
        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} onReplay={playAudio} />
        ))}

        {thinking && (
          <div className="flex justify-start">
            <div className="bg-muted text-foreground rounded-2xl rounded-bl-md px-3 py-1.5 animate-pulse text-sm">
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

// ── 页面快照提取（通过 chrome.scripting.executeScript 在页面上下文执行）──

const SNAPSHOT_FN = () => {
  const selection = window.getSelection()?.toString() || '';
  let context = '';
  if (selection) {
    const sel = window.getSelection();
    if (sel && sel.rangeCount) {
      const range = sel.getRangeAt(0);
      const BLOCK_TAGS = [
        'P', 'DIV', 'SECTION', 'ARTICLE', 'LI',
        'H1', 'H2', 'H3', 'H4', 'H5', 'H6',
        'BLOCKQUOTE', 'PRE', 'TD',
      ];
      let el: Element | null =
        range.commonAncestorContainer.nodeType === 3
          ? (range.commonAncestorContainer as Text).parentElement
          : (range.commonAncestorContainer as Element);
      while (el) {
        if (BLOCK_TAGS.includes(el.tagName)) break;
        el = el.parentElement;
      }
      if (el) {
        context = (el.textContent || '').slice(0, 500);
      } else {
        const full = document.body.innerText;
        const start = Math.max(0, range.startOffset - 250);
        context = full.slice(start, start + 500);
      }
    }
  }
  return { selection, context, url: location.href, title: document.title } as PageSnapshot;
};

async function captureSnapshot(tabId?: number): Promise<PageSnapshot> {
  const tid = tabId || (await getActiveTabId());
  // 先 fallback: 扩展自身上下文中 window.getSelection()
  const ownSelection = window.getSelection()?.toString();
  const ownUrl = location.href;
  if (ownSelection && ownUrl !== 'chrome-extension://') {
    // 可能在开发/测试模式下 sidecar 自身有选词
    let context = '';
    const sel = window.getSelection();
    if (sel && sel.rangeCount) {
      const range = sel.getRangeAt(0);
      const el =
        range.commonAncestorContainer.nodeType === 3
          ? (range.commonAncestorContainer as Text).parentElement
          : (range.commonAncestorContainer as Element);
      if (el) {
        context = (el.textContent || '').slice(0, 500);
      }
    }
    return { selection: ownSelection, context, url: ownUrl, title: document.title };
  }
  // 通过 scripting 在页面上下文提取
  try {
    const [result] = await chrome.scripting.executeScript({
      target: { tabId: tid },
      func: SNAPSHOT_FN,
    });
    return result.result as PageSnapshot;
  } catch {
    return { selection: '', context: '', url: '', title: '' };
  }
}

async function getActiveTabId(): Promise<number> {
  const tab = (await chrome.tabs.query({ active: true, currentWindow: true }))[0];
  return tab?.id ?? 0;
}
