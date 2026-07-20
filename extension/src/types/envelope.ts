export type TaskKind = 'translate' | 'look_up' | 'none';
export type SurfaceKind = 'sidecar' | 'popup' | 'fullscreen';
export type SourceKind = 'plain' | 'web' | 'pdf' | 'epub' | 'ios_app';

export interface ChatPart {
  message: string;
}

export interface SelectionPart {
  text: string;
}

export interface ScreenshotPart {
  data_url: string;
  mime: string;
}

export interface ContextPart {
  text: string;
  kind: 'paragraph' | 'page' | 'screen' | 'plain';
  screenshot?: ScreenshotPart;
}

export interface SourcePlain {
  kind: 'plain';
}

export interface SourceWeb {
  kind: 'web';
  url: string;
  title: string;
  surface: SurfaceKind;
}

export type SourcePart = SourcePlain | SourceWeb;

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
  selection: SelectionPart;
  context: ContextPart;
  source: SourcePart;
  device?: DevicePart;
}

export function buildEnvelope(
  task: TaskKind,
  chatMessage: string,
  snapshot: {
    selection: string;
    context: string;
    url: string;
    title: string;
    deviceId?: string;
  },
): UserInputEnvelope {
  return {
    schema_version: 1,
    task,
    chat: { message: chatMessage },
    selection: { text: snapshot.selection },
    context: {
      text: snapshot.context,
      kind: snapshot.context ? 'paragraph' : 'plain',
    },
    source: {
      kind: 'web',
      url: snapshot.url,
      title: snapshot.title,
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
