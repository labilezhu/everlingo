import type { Message } from '@/types/chat';

const STORAGE_KEY = 'chatbot:state';

export const MAX_STORED_MESSAGES = 100;

export interface ChatState {
  sessionId: string;
  messages: Message[];
}

function stripAudioUrl(msg: Message): Message {
  if (msg.audioUrl) {
    const { audioUrl: _audioUrl, ...rest } = msg;
    return rest;
  }
  return msg;
}

export function loadChatState(): ChatState | null {
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<ChatState>;
    if (typeof parsed.sessionId !== 'string' || !Array.isArray(parsed.messages)) return null;
    const messages = (parsed.messages as Message[]).map(stripAudioUrl);
    return { sessionId: parsed.sessionId, messages };
  } catch {
    return null;
  }
}

export function saveChatState(state: ChatState): void {
  const write = (payload: unknown): boolean => {
    try {
      window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
      return true;
    } catch {
      return false;
    }
  };
  const cleanMessages = state.messages.map(stripAudioUrl);
  if (write({ sessionId: state.sessionId, messages: cleanMessages })) return;
  if (write({ sessionId: state.sessionId, messages: cleanMessages.slice(-MAX_STORED_MESSAGES) })) return;
  write({ sessionId: state.sessionId, messages: [] });
}
