export type TaskKind = 'translate' | 'look_up' | 'none';
export type SurfaceKind = 'sidecar' | 'popup' | 'fullscreen';
export type SourceKind = 'plain' | 'web' | 'chrome_ext' | 'pdf' | 'epub' | 'ios_app';

export interface ChatPart {
  message: string;
}

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

export interface ChatContextPart {
  resource_contexts: ResourceContext[];
}

export interface SourcePlain {
  kind: 'plain';
}

export interface SourceWeb {
  kind: 'web';
  url: string;
  title: string;
  surface: 'fullscreen';
}

export interface SourceChromeExt {
  kind: 'chrome_ext';
  url: string;
  title: string;
  surface: 'sidecar' | 'popup';
}

export type SourcePart = SourcePlain | SourceWeb | SourceChromeExt;

export interface DevicePart {
  platform: 'chrome_ext' | 'ios_app' | 'pdf_reader' | 'web' | 'cli';
  device_id?: string;
  locale?: string;
  timezone?: string;
}

export interface UserInputEnvelope {
  schema_version: 1;
  task: TaskKind;
  chat: ChatPart;
  chat_context: ChatContextPart;
  source: SourcePart;
  device?: DevicePart;
}

export function buildEnvelope(
  task: TaskKind,
  chatMessage: string,
  snapshot: {
    text: string;
    paragraph_text: string;
    url?: string;
    title?: string;
    deviceId?: string;
  },
): UserInputEnvelope {
  const resource_contexts: ResourceContext[] = [];
  if (snapshot.text) {
    resource_contexts.push({
      kind: 'selected_text',
      text: snapshot.text,
      paragraph_text: snapshot.paragraph_text || null,
    });
  }
  return {
    schema_version: 1,
    task,
    chat: { message: chatMessage },
    chat_context: { resource_contexts },
    source: {
      kind: 'chrome_ext',
      url: snapshot.url ?? '',
      title: snapshot.title ?? '',
      surface: 'sidecar',
    },
    device: {
      platform: 'chrome_ext',
      device_id: snapshot.deviceId,
      locale: navigator.language,
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    },
  };
}
