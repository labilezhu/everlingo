export type TaskKind = 'translate' | 'look_up' | 'none';

export type ResourceContext =
  | { kind: 'vault_file'; file_path: string }
  | { kind: 'web_page'; url: string; title?: string }
  | {
      kind: 'selected_text';
      text: string;
      start_line?: number | null;
      start_column?: number | null;
      paragraph_text?: string | null;
    };

export interface UserInputEnvelope {
  schema_version: number;
  task: TaskKind;
  chat: { message: string };
  chat_context: { resource_contexts: ResourceContext[] };
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
  from: 'user' | 'bot' | 'system';
  audioUrl?: string;
}

export interface SSEEvent {
  type: 'message' | 'typing_hint' | 'sound';
  data: Record<string, unknown>;
}

export function uid(): string {
  return Math.random().toString(36).slice(2, 10);
}
