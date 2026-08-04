import type { TaskKind, UserInputEnvelope, SSEEvent, ResourceContext } from '@/types/chat';
import { apiFetchJson } from './apiFetch';

export type ConnStatus =
  | { state: 'connected' }
  | { state: 'reconnecting'; attempt: number; countdown: number }
  | { state: 'session_expired' };

export interface ConnectSSEResult {
  cleanup: () => void;
  retryNow: () => void;
}

export function buildEnvelope(task: TaskKind, message: string, resourceContexts: ResourceContext[] = []): UserInputEnvelope {
  return {
    schema_version: 1,
    task,
    chat: { message },
    chat_context: { resource_contexts: resourceContexts },
    source: {
      kind: 'web',
      surface: 'fullscreen',
      url: window.location.href,
      title: document.title,
    },
    device: {
      platform: 'web',
      locale: navigator.language,
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    },
  };
}

export async function createSession(): Promise<string> {
  const data = await apiFetchJson<{ session_id: string }>('/api/session', { method: 'POST' });
  return data.session_id;
}

export async function sendMessage(sessionId: string, envelope: UserInputEnvelope): Promise<void> {
  await apiFetchJson(`/api/session/${sessionId}/message`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ envelope }),
  });
}

const MAX_BACKOFF_MS = 30_000;

export function connectSSE(
  sessionId: string,
  onEvent: (e: SSEEvent) => void,
  onStatus: (s: ConnStatus) => void,
): ConnectSSEResult {
  let es: EventSource | null = null;
  let retryTimer: ReturnType<typeof setTimeout> | null = null;
  let countdownTimer: ReturnType<typeof setInterval> | null = null;
  let attempt = 0;
  let closed = false;

  function backoffMs(): number {
    return Math.min(1000 * Math.pow(2, attempt), MAX_BACKOFF_MS);
  }

  function clearCountdown() {
    if (countdownTimer !== null) {
      clearInterval(countdownTimer);
      countdownTimer = null;
    }
  }

  function setupEventSource() {
    es = new EventSource(`/api/session/${sessionId}/events`);

    es.addEventListener('message', (e: MessageEvent) => {
      try { onEvent({ type: 'message', data: JSON.parse(e.data) }); } catch { /* skip */ }
    });
    es.addEventListener('typing_hint', (e: MessageEvent) => {
      try { onEvent({ type: 'typing_hint', data: JSON.parse(e.data) }); } catch { /* skip */ }
    });
    es.addEventListener('sound', (e: MessageEvent) => {
      try { onEvent({ type: 'sound', data: JSON.parse(e.data) }); } catch { /* skip */ }
    });

    es.onopen = () => {
      attempt = 0;
      clearCountdown();
      onStatus({ state: 'connected' });
    };

    es.onerror = () => {
      const wasRejected = es?.readyState === EventSource.CLOSED;
      if (es) {
        es.close();
        es = null;
      }
      if (wasRejected) {
        closed = true;
        onStatus({ state: 'session_expired' });
      } else {
        scheduleRetry();
      }
    };
  }

  function scheduleRetry() {
    if (closed) return;
    attempt++;
    const delay = backoffMs();
    let remaining = Math.ceil(delay / 1000);

    onStatus({ state: 'reconnecting', attempt, countdown: remaining });

    countdownTimer = setInterval(() => {
      remaining--;
      if (remaining >= 0) {
        onStatus({ state: 'reconnecting', attempt, countdown: remaining });
      }
    }, 1000);

    retryTimer = setTimeout(() => {
      clearCountdown();
      setupEventSource();
    }, delay);
  }

  function cleanup() {
    closed = true;
    if (es) {
      es.close();
      es = null;
    }
    if (retryTimer !== null) {
      clearTimeout(retryTimer);
      retryTimer = null;
    }
    clearCountdown();
  }

  function retryNow() {
    if (retryTimer !== null) {
      clearTimeout(retryTimer);
      retryTimer = null;
    }
    clearCountdown();
    if (es) {
      es.close();
      es = null;
    }
    setupEventSource();
  }

  setupEventSource();

  return { cleanup, retryNow };
}
