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
import { getApiBaseUrl } from '@/config';

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
  const baseUrlRef = useRef<string>('');
  const cleanupRef = useRef<(() => void) | undefined>(undefined);

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

  // ── TRIGGER_TRANSLATE 消息监听（来自 background） ──────────────
  useEffect(() => {
    const handler = (msg: { type?: string; task?: TaskKind }) => {
      if (msg.type !== 'TRIGGER_TRANSLATE') return;
      handleTriggerTranslate();
    };
    chrome.runtime.onMessage.addListener(handler);
    return () => chrome.runtime.onMessage.removeListener(handler);
  }, []);

  async function handleTriggerTranslate() {
    const sid = sessionIdRef.current;
    const base = baseUrlRef.current;
    if (!sid) return;

    const snapshot = await captureSnapshot();
    snapshotRef.current = snapshot;
    if (!snapshot.selection) return;

    setPending(true);
    try {
      const env = buildEnvelope('translate', '', {
        ...snapshot,
        deviceId: deviceIdRef.current,
      });
      await sendEnvelope(base, sid, env);
      await appendMessage(tabIdRef.current, {
        role: 'user',
        text: '',
        timestamp: new Date().toISOString(),
      });
    } catch {
      setPending(false);
      setError('翻译失败');
    }
  }

  // ── tab 切换刷新 ────────────────────────────────────────────
  async function switchToTab() {
    cleanupRef.current?.();
    cleanupRef.current = undefined;
    setThinking(false);
    setPending(false);

    const { sessionId: sid, fresh, tabId: newTabId } = await getSession();
    setSessionId(sid);
    sessionIdRef.current = sid;
    tabIdRef.current = newTabId;

    const defaultMsg: Message = {
      id: uid(),
      text: '你好！我是小记🐹，你的 AI 外语老师。有什么可以帮你的吗？',
      from: 'bot',
    };
    if (fresh) {
      setMessages([defaultMsg]);
    } else {
      const history = await loadHistory(newTabId);
      setMessages([
        defaultMsg,
        ...history.map((h) => ({
          id: uid(),
          text: h.text,
          from: h.role === 'user' ? 'user' as const : 'bot' as const,
        })),
      ]);
    }

    cleanupRef.current = connectSSE(
      baseUrlRef.current,
      sid,
      (e: SSEEvent) => handleSSEEvent(e, newTabId),
      () => { setError('连接断开，请刷新页面重试'); },
    );
  }

  // ── tabs.onActivated 监听（切 tab 时刷新内容） ────────────────
  useEffect(() => {
    const handler = async (activeInfo: { tabId: number; windowId: number }) => {
      const win = await chrome.windows.getCurrent();
      if (activeInfo.windowId !== (win.id ?? -1)) return;
      try { await switchToTab(); }
      catch { setError('切换 tab 失败'); }
    };
    chrome.tabs.onActivated.addListener(handler);
    return () => chrome.tabs.onActivated.removeListener(handler);
  }, []);

  // ── 初始化 ──────────────────────────────────────────────────
  useEffect(() => {
    (async () => {
      try {
        baseUrlRef.current = await getApiBaseUrl();
        const { device_id } = await chrome.storage.local.get('device_id');
        deviceIdRef.current = device_id || '';

        await switchToTab();

        const sid = sessionIdRef.current;
        if (!sid) return;

        const snapshot = await captureSnapshot();
        snapshotRef.current = snapshot;

        if (snapshot.selection) {
          setPending(true);
          try {
            const env = buildEnvelope(task, '', {
              ...snapshot,
              deviceId: deviceIdRef.current,
            });
            await sendEnvelope(baseUrlRef.current, sid, env);
            await appendMessage(tabIdRef.current, {
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
      cleanupRef.current?.();
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
      const base = baseUrlRef.current;
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
        await sendEnvelope(base, sid, env);
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
