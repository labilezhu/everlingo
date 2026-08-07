import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { NotebookPen } from 'lucide-react';
import MessageBubble from './MessageBubble';
import ChatInput from './ChatInput';
import TaskSelector from './TaskSelector';
import { Button } from '@/components/ui/button';
import { connectSSE, sendEnvelope, type ConnStatus } from '@/services/sseClient';
import { getSession } from '@/services/backgroundClient';
import { loadHistory, appendMessage, clearHistory } from '@/services/messageHistory';
import { buildEnvelope, type TaskKind } from '@/types/envelope';
import type { Message, SSEEvent } from '@/types/chat';
import { uid } from '@/types/chat';
import { getApiConfig } from '@/config';
import { extractContextText } from '@/content/extract';

interface PageSnapshot {
  text: string;
  paragraph_text: string;
  url?: string;
  title?: string;
}

export default function ChatWindow() {
  const { t } = useTranslation('chatbot');
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [task, setTask] = useState<TaskKind>('translate');
  const [messages, setMessages] = useState<Message[]>([
    { id: uid(), text: t('welcome_text'), from: 'bot' },
  ]);
  const [thinking, setThinking] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [connStatus, setConnStatus] = useState<ConnStatus | null>(null);
  const retryNowRef = useRef<(() => void) | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const snapshotRef = useRef<PageSnapshot>({
    text: '', paragraph_text: '', url: '', title: '',
  });
  const sessionIdRef = useRef<string | null>(null);
  const tabIdRef = useRef<number>(0);
  const deviceIdRef = useRef<string>('');
  const baseUrlRef = useRef<string>('');
  const authHeaderRef = useRef<string | null>(null);
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
    const auth = authHeaderRef.current;
    if (!sid) return;

    const snapshot = await captureSnapshot();
    snapshotRef.current = snapshot;
    if (!snapshot.text) return;

    setPending(true);
    try {
      const env = buildEnvelope('translate', '', {
        text: snapshot.text,
        paragraph_text: snapshot.paragraph_text,
        url: snapshot.url,
        title: snapshot.title,
        deviceId: deviceIdRef.current,
      });
      await sendEnvelope(base, sid, env, auth);
      await appendMessage(tabIdRef.current, {
        role: 'user',
        text: '',
        timestamp: new Date().toISOString(),
      });
    } catch {
      setPending(false);
      setError(t('translate_failed'));
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
      text: t('welcome_text'),
      from: 'bot',
    };
    if (fresh) {
      setMessages([defaultMsg]);
    } else {
      const history = await loadHistory(newTabId);
      setMessages([
        defaultMsg,
        ...history.map((h) => {
          const from: Message['from'] = h.role === 'user' ? 'user' : h.role === 'system' ? 'system' : 'bot';
          return { id: uid(), text: h.text, from };
        }),
      ]);
    }

    const conn = connectSSE(
      baseUrlRef.current,
      sid,
      (e: SSEEvent) => handleSSEEvent(e, newTabId),
      (s: ConnStatus) => setConnStatus(s),
      authHeaderRef.current,
    );
    cleanupRef.current = conn.cleanup;
    retryNowRef.current = conn.retryNow;
  }

  async function handleRebuild() {
    setConnStatus(null);
    cleanupRef.current?.();
    cleanupRef.current = undefined;
    setThinking(false);
    setPending(false);

    const systemMsg: Message = {
      id: uid(),
      text: t('session_reset_note'),
      from: 'system',
    };
    setMessages((prev) => [...prev, systemMsg]);

    try {
      const { sessionId: sid, tabId: newTabId } = await getSession();
      setSessionId(sid);
      sessionIdRef.current = sid;
      tabIdRef.current = newTabId;

      await appendMessage(newTabId, {
        role: 'system',
        text: systemMsg.text,
        timestamp: new Date().toISOString(),
      });

      const conn = connectSSE(
        baseUrlRef.current,
        sid,
        (e: SSEEvent) => handleSSEEvent(e, newTabId),
        (s: ConnStatus) => setConnStatus(s),
        authHeaderRef.current,
      );
      cleanupRef.current = conn.cleanup;
      retryNowRef.current = conn.retryNow;
    } catch {
      setError(t('reconnect_failed'));
    }
  }

  // ── tabs.onActivated 监听（切 tab 时刷新内容） ────────────────
  useEffect(() => {
    const handler = async (activeInfo: { tabId: number; windowId: number }) => {
      const win = await chrome.windows.getCurrent();
      if (activeInfo.windowId !== (win.id ?? -1)) return;
      try { await switchToTab(); }
      catch { setError(t('switch_tab_failed')); }
    };
    chrome.tabs.onActivated.addListener(handler);
    return () => chrome.tabs.onActivated.removeListener(handler);
  }, []);

  // ── 初始化 ──────────────────────────────────────────────────
  useEffect(() => {
    (async () => {
      try {
        const config = await getApiConfig();
        baseUrlRef.current = config.baseUrl;
        authHeaderRef.current = config.authHeader;
        const { device_id } = await chrome.storage.local.get('device_id');
        deviceIdRef.current = device_id || '';

        await switchToTab();

        const sid = sessionIdRef.current;
        if (!sid) return;

        const snapshot = await captureSnapshot();
        snapshotRef.current = snapshot;

        if (snapshot.text) {
          setPending(true);
          try {
            const env = buildEnvelope(task, '', {
              text: snapshot.text,
              paragraph_text: snapshot.paragraph_text,
              url: snapshot.url,
              title: snapshot.title,
              deviceId: deviceIdRef.current,
            });
            await sendEnvelope(baseUrlRef.current, sid, env, authHeaderRef.current);
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
        setError(t('connect_failed'));
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
      const auth = authHeaderRef.current;
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
        const snap = snapshotRef.current;
        const env = buildEnvelope(task, text, {
          text: snap.text,
          paragraph_text: snap.paragraph_text,
          url: snap.url,
          title: snap.title,
          deviceId: deviceIdRef.current,
        });
        await sendEnvelope(base, sid, env, auth);
      } catch {
        setPending(false);
        setError(t('send_failed'));
      }
    },
    [task],
  );

  return (
    <div className="flex flex-col h-screen border-x border-border bg-background">
      <header className="flex items-center justify-between gap-2 px-3 py-2 border-b border-border">
        <div className="flex items-center gap-2">
          <span className="text-lg">🐹</span>
          <h1 className="text-base font-semibold text-foreground">{t('app_name')}</h1>
        </div>
        <Button variant="ghost" size="sm" onClick={() => {
          chrome.tabs.create({ url: `${baseUrlRef.current}/editor` });
        }}>
          <NotebookPen />
          <span>{t('notes')}</span>
        </Button>
      </header>

      <TaskSelector task={task} onChange={setTask} />

      {error && (
        <div className="px-3 py-1.5 bg-red-50 text-red-600 text-xs border-b border-red-200">
          {error}
        </div>
      )}

      {connStatus?.state === 'reconnecting' && (
        <div className="px-3 py-1.5 bg-amber-50 text-amber-700 text-xs border-b border-amber-200 flex items-center justify-between gap-2">
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
        <div className="px-3 py-1.5 bg-amber-50 text-amber-700 text-xs border-b border-amber-200 flex items-center justify-between gap-2">
          <span>{t('session_expired')}</span>
          <button
            onClick={handleRebuild}
            className="underline whitespace-nowrap font-medium shrink-0"
          >
            {t('restart')}
          </button>
        </div>
      )}

      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-3">
        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} onReplay={playAudio} />
        ))}

        {thinking && (
          <div className="flex justify-start">
            <div className="bg-muted text-foreground rounded-2xl rounded-bl-md px-3 py-1.5 animate-pulse text-sm">
              {t('thinking')}
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
  const text = window.getSelection()?.toString() || '';
  let paragraph_text = '';
  if (text) {
    const sel = window.getSelection();
    if (sel && sel.rangeCount) {
      const range = sel.getRangeAt(0);
      const BLOCK_TAGS = [
        'P', 'DIV', 'SECTION', 'ARTICLE', 'LI',
        'H1', 'H2', 'H3', 'H4', 'H5', 'H6',
        'BLOCKQUOTE', 'PRE', 'TD',
      ];
      const MAX_LEN = 500;
      let block: Element | null = range.commonAncestorContainer as Element;
      while (block && !(block.tagName && BLOCK_TAGS.includes(block.tagName.toUpperCase()))) {
        block = block.parentElement;
      }
      const sourceText = block ? block.textContent || '' : document.body.textContent || '';
      if (sourceText.length <= MAX_LEN) {
        paragraph_text = sourceText;
      } else {
        // 与 extract.ts 的 textContentOffset 保持一致：用 TreeWalker 按文档序
        // 累加 text 节点长度，计算选词在 sourceText 中的字符偏移
        let pos = 0;
        const root: Node = block ?? document.body;
        const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
        let node: Node | null;
        while ((node = walker.nextNode())) {
          if (node === range.startContainer) {
            pos += range.startOffset;
            break;
          }
          pos += node.textContent ? node.textContent.length : 0;
        }
        const selText = sel.toString();
        if (!selText) {
          paragraph_text = sourceText.slice(0, MAX_LEN);
        } else {
          const selLen = Math.min(selText.length, MAX_LEN);
          let start = Math.max(0, pos - Math.floor((MAX_LEN - selLen) / 2));
          let end = start + MAX_LEN;
          if (end > sourceText.length) {
            end = sourceText.length;
            start = Math.max(0, end - MAX_LEN);
          }
          paragraph_text = sourceText.slice(start, end);
        }
      }
    }
  }
  return { text, paragraph_text } as PageSnapshot;
};

async function captureSnapshot(tabId?: number): Promise<PageSnapshot> {
  const activeTab = await getActiveTab(tabId);
  const tid = activeTab?.id ?? 0;
  const ownText = window.getSelection()?.toString();
  if (ownText) {
    const sel = window.getSelection();
    const paragraph_text = sel && sel.rangeCount ? extractContextText(sel) : '';
    return { text: ownText, paragraph_text, url: activeTab?.url, title: activeTab?.title };
  }
  try {
    const [result] = await chrome.scripting.executeScript({
      target: { tabId: tid },
      func: SNAPSHOT_FN,
    });
    return {
      text: (result.result as PageSnapshot).text,
      paragraph_text: (result.result as PageSnapshot).paragraph_text,
      url: activeTab?.url,
      title: activeTab?.title,
    };
  } catch {
    return { text: '', paragraph_text: '', url: activeTab?.url, title: activeTab?.title };
  }
}

async function getActiveTab(tabId?: number): Promise<chrome.tabs.Tab | undefined> {
  if (tabId) {
    const tab = await chrome.tabs.get(tabId).catch(() => undefined);
    if (tab) return tab;
  }
  return (await chrome.tabs.query({ active: true, currentWindow: true }))[0];
}
