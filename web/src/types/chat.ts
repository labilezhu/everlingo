export interface Message {
  id: string;
  text: string;
  from: 'user' | 'bot';
  audioUrl?: string;
}

export interface SSEEvent {
  type: 'message' | 'typing_hint' | 'sound';
  data: Record<string, unknown>;
}

export function uid(): string {
  return Math.random().toString(36).slice(2, 10);
}
