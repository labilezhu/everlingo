import type { SSEEvent } from '@/types/chat';

export async function createSession(): Promise<string> {
  const res = await fetch('/api/session', { method: 'POST' });
  if (!res.ok) throw new Error('Failed to create session');
  const data = await res.json();
  return data.session_id as string;
}

export async function sendMessage(sessionId: string, text: string): Promise<void> {
  const res = await fetch(`/api/session/${sessionId}/message`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  });
  if (!res.ok) throw new Error('Failed to send message');
}

export function connectSSE(
  sessionId: string,
  onEvent: (e: SSEEvent) => void,
  onError?: () => void,
): () => void {
  const es = new EventSource(`/api/session/${sessionId}/events`);

  es.addEventListener('message', (e: MessageEvent) => {
    try { onEvent({ type: 'message', data: JSON.parse(e.data) }); } catch { /* skip */ }
  });
  es.addEventListener('typing_hint', (e: MessageEvent) => {
    try { onEvent({ type: 'typing_hint', data: JSON.parse(e.data) }); } catch { /* skip */ }
  });
  es.addEventListener('sound', (e: MessageEvent) => {
    try { onEvent({ type: 'sound', data: JSON.parse(e.data) }); } catch { /* skip */ }
  });
  es.onerror = () => onError?.();

  return () => es.close();
}
