import { API_BASE_URL } from '@/config';

// ── 安装时生成 device_id ──────────────────────────────────────
chrome.runtime.onInstalled.addListener(async () => {
  const { device_id } = await chrome.storage.local.get('device_id');
  if (!device_id) {
    await chrome.storage.local.set({ device_id: crypto.randomUUID() });
  }
});

// ── 点击扩展图标 → 打开 sidecar panel ────────────────────────
chrome.action.onClicked.addListener((tab) => {
  if (tab.id != null) {
    chrome.sidePanel.open({ tabId: tab.id });
  }
});

// ── 消息处理 ──────────────────────────────────────────────────
interface GetSessionResponse {
  sessionId: string;
  fresh: boolean;
  tabId: number;
  error?: boolean;
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type === 'GET_SESSION') {
    handleGetSession()
      .then((r: GetSessionResponse) => sendResponse(r))
      .catch(() => sendResponse({ error: true } as GetSessionResponse));
    return true; // async response
  }
  return false;
});

// ── GET_SESSION 处理 ──────────────────────────────────────────
async function handleGetSession(): Promise<GetSessionResponse> {
  const tab = (await chrome.tabs.query({ active: true, currentWindow: true }))[0];
  if (!tab?.id) {
    throw new Error('No active tab');
  }
  const tabId = tab.id;
  const sidKey = `sid:${tabId}`;
  const { [sidKey]: existingSid } = await chrome.storage.session.get(sidKey);

  if (typeof existingSid === 'string') {
    const ok = await probeSession(existingSid);
    if (ok) {
      return { sessionId: existingSid, fresh: false, tabId };
    }
  }

  // 新建 session：先清除旧 UI history，再 POST
  await chrome.storage.session.remove([`msgs:${tabId}`, sidKey]);
  const newSid = await createSession();
  await chrome.storage.session.set({ [sidKey]: newSid });
  return { sessionId: newSid, fresh: true, tabId };
}

async function probeSession(sid: string): Promise<boolean> {
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 3000);
    const res = await fetch(`${API_BASE_URL}/api/session/${sid}/events`, {
      method: 'GET',
      headers: { Accept: 'text/event-stream' },
      signal: controller.signal,
    });
    clearTimeout(timer);
    return res.ok;
  } catch {
    return false;
  }
}

async function createSession(): Promise<string> {
  const res = await fetch(`${API_BASE_URL}/api/session`, { method: 'POST' });
  if (!res.ok) {
    throw new Error(`Failed to create session: ${res.status}`);
  }
  const data = await res.json();
  return data.session_id as string;
}
