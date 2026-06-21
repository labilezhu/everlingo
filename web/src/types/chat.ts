export interface Message {
  id: string;
  text: string;
  from: 'user' | 'bot';
}

export interface SSEEvent {
  type: 'message' | 'typing_hint';
  data: Record<string, unknown>;
}

export function uid(): string {
  return Math.random().toString(36).slice(2, 10);
}
