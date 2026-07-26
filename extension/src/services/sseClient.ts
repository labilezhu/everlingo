import { fetchEventSource } from '@microsoft/fetch-event-source';
import type { UserInputEnvelope } from '@/types/envelope';
import type { SSEEvent } from '@/types/chat';

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

export function connectSSE(
  baseUrl: string,
  sessionId: string,
  onEvent: (e: SSEEvent) => void,
  onError?: () => void,
  authHeader?: string | null,
): () => void {
  const abortController = new AbortController();

  const headers: Record<string, string> = {};
  if (authHeader) {
    headers['Authorization'] = authHeader;
  }

  fetchEventSource(`${baseUrl}/api/session/${sessionId}/events`, {
    signal: abortController.signal,
    headers,
    openWhenHidden: true,
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
      onError?.();
      return 0; // stop reconnection
    },
  });

  return () => abortController.abort();
}
