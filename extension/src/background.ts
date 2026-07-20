import { getApiBaseUrl } from '@/config';

// ── 安装时生成 device_id + 创建右键菜单 + 设全局 side panel ──────────
chrome.runtime.onInstalled.addListener(async () => {
  await chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true });

  const { device_id } = await chrome.storage.local.get('device_id');
  if (!device_id) {
    await chrome.storage.local.set({ device_id: crypto.randomUUID() });
  }

  chrome.contextMenus.create({
    id: 'translate-selection',
    title: '用小记🐹翻译',
    contexts: ['selection'],
  });
});

// ── 右键菜单点击 ──────────────────────────────────────────────
chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === 'translate-selection' && tab?.id != null) {
    triggerTranslate(tab.id);
  }
});

// ── 触发翻译：打开 sidecar（全局 panel，右键菜单时确保可见）→ sidecar 注册了 TRIGGER_TRANSLATE 监听 ──
async function triggerTranslate(tabId: number) {
  await chrome.sidePanel.open({ tabId });  // 全局 panel（setPanelBehavior 控制），tabId 仅用于定位窗口
  try {
    await chrome.runtime.sendMessage({ type: 'TRIGGER_TRANSLATE', task: 'translate' });
  } catch {
    // sidecar panel 尚未就绪时忽略（init 流程会处理首次抓取+发送）
  }
}

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
    const base = await getApiBaseUrl();
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 3000);
    const res = await fetch(`${base}/api/session/${sid}/events`, {
      method: 'GET',
      headers: { Accept: 'text/event-stream' },
      signal: controller.signal,
    });
    clearTimeout(timer);
    controller.abort(); // 拿到响应头后立即关闭流，避免 SSE 长连接残留
    return res.ok;
  } catch {
    return false;
  }
}

async function createSession(): Promise<string> {
  const base = await getApiBaseUrl();
  const res = await fetch(`${base}/api/session`, { method: 'POST' });
  if (!res.ok) {
    throw new Error(`Failed to create session: ${res.status}`);
  }
  const data = await res.json();
  return data.session_id as string;
}
