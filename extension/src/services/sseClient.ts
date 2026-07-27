import { fetchEventSource } from '@microsoft/fetch-event-source';
import type { UserInputEnvelope } from '@/types/envelope';
import type { SSEEvent } from '@/types/chat';

export type ConnStatus =
  | { state: 'connected' }
  | { state: 'reconnecting'; attempt: number; countdown: number }
  | { state: 'session_expired' };

export interface ConnectSSEResult {
  cleanup: () => void;
  retryNow: () => void;
}

export async function sendEnvelope(
  baseUrl: string,
  sessionId: string,
  env: UserInputEnvelope,
  authHeader?: string | null,
): Promise<void> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (authHeader) {
    headers['Authorization'] = authHeader;
  }
  const res = await fetch(`${baseUrl}/api/session/${sessionId}/message`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ envelope: env }),
  });
  if (!res.ok) throw new Error('Failed to send envelope');
}

class SessionExpiredError extends Error {
  constructor() {
    super('Session expired');
    this.name = 'SessionExpiredError';
  }
}

const MAX_BACKOFF_MS = 30_000;

export function connectSSE(
  baseUrl: string,
  sessionId: string,
  onEvent: (e: SSEEvent) => void,
  onStatus: (s: ConnStatus) => void,
  authHeader?: string | null,
): ConnectSSEResult {
  let abortController = new AbortController();
  let retryTimer: ReturnType<typeof setTimeout> | null = null;
  let countdownTimer: ReturnType<typeof setInterval> | null = null;
  let attempt = 0;
  let closed = false;

  const headers: Record<string, string> = {};
  if (authHeader) {
    headers['Authorization'] = authHeader;
  }

  function backoffMs(): number {
    return Math.min(1000 * Math.pow(2, attempt), MAX_BACKOFF_MS);
  }

  function clearCountdown() {
    if (countdownTimer !== null) {
      clearInterval(countdownTimer);
      countdownTimer = null;
    }
  }

  function startConnection() {
    abortController = new AbortController();
    fetchEventSource(`${baseUrl}/api/session/${sessionId}/events`, {
      signal: abortController.signal,
      headers,
      openWhenHidden: true,
      async onopen(response) {
        if (response.status === 404) {
          throw new SessionExpiredError();
        }
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const contentType = response.headers.get('content-type');
        if (!contentType?.startsWith('text/event-stream')) {
          throw new Error(`Expected content-type text/event-stream, Actual: ${contentType}`);
        }
        attempt = 0;
        clearCountdown();
        onStatus({ state: 'connected' });
      },
      onmessage(msg) {
        try {
          const parsed = JSON.parse(msg.data);
          if (msg.event === 'typing_hint') {
            onEvent({ type: 'typing_hint', data: parsed });
          } else if (msg.event === 'sound') {
            onEvent({ type: 'sound', data: parsed });
          } else {
            onEvent({ type: 'message', data: parsed });
          }
        } catch { /* skip */ }
      },
      onerror(err) {
        if (err instanceof SessionExpiredError) {
          closed = true;
          clearCountdown();
          onStatus({ state: 'session_expired' });
          throw err;
        }
        if (closed) return;
        scheduleRetry();
        throw new Error('take over retry');
      },
    }).catch(() => {});
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
      startConnection();
    }, delay);
  }

  function cleanup() {
    closed = true;
    abortController.abort();
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
    abortController.abort();
    if (!closed) {
      attempt = 0;
      startConnection();
    }
  }

  startConnection();

  return { cleanup, retryNow };
}
