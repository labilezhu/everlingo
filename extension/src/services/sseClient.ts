import type { UserInputEnvelope } from '@/types/envelope';
import type { SSEEvent } from '@/types/chat';

export async function sendEnvelope(
  baseUrl: string,
  sessionId: string,
  env: UserInputEnvelope,
): Promise<void> {
  const res = await fetch(`${baseUrl}/api/session/${sessionId}/message`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ envelope: env }),
  });
  if (!res.ok) throw new Error('Failed to send envelope');
}

export function connectSSE(
  baseUrl: string,
  sessionId: string,
  onEvent: (e: SSEEvent) => void,
  onError?: () => void,
): () => void {
  const es = new EventSource(`${baseUrl}/api/session/${sessionId}/events`);

  es.addEventListener('message', (e: MessageEvent) => {
    try {
      onEvent({ type: 'message', data: JSON.parse(e.data) });
    } catch { /* skip */ }
  });
  es.addEventListener('typing_hint', (e: MessageEvent) => {
    try {
      onEvent({ type: 'typing_hint', data: JSON.parse(e.data) });
    } catch { /* skip */ }
  });
  es.addEventListener('sound', (e: MessageEvent) => {
    try {
      onEvent({ type: 'sound', data: JSON.parse(e.data) });
    } catch { /* skip */ }
  });
  es.onerror = () => onError?.();

  return () => es.close();
}
