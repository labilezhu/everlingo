export type TaskKind = 'translate' | 'look_up' | 'none';

export interface UserInputEnvelope {
  schema_version: number;
  task: TaskKind;
  chat: { message: string };
  selection: { text: string };
  context: { text: string };
  source: {
    kind: 'web';
    surface: 'fullscreen';
    url: string;
    title: string;
  };
  device: {
    platform: 'web';
    locale: string;
    timezone: string;
  };
}

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
