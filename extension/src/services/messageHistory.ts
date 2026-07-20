const HISTORY_LIMIT_BYTES = 10 * 1024 * 1024; // 10MB

export interface UIMessageRecord {
  role: 'user' | 'assistant';
  text: string;
  timestamp: string;
}

export async function loadHistory(tabId: number): Promise<UIMessageRecord[]> {
  const key = `msgs:${tabId}`;
  const { [key]: msgs } = await chrome.storage.session.get(key);
  return (msgs as UIMessageRecord[]) || [];
}

export async function appendMessage(
  tabId: number,
  record: UIMessageRecord,
): Promise<void> {
  const key = `msgs:${tabId}`;
  const existing = await loadHistory(tabId);

  // 去重：同 role+timestamp 不重复添加（SSE 重连可能重复推送）
  if (
    record.role === 'assistant' &&
    existing.some(
      (m) => m.role === 'assistant' && m.timestamp === record.timestamp,
    )
  ) {
    return;
  }

  const next = [...existing, record];
  // FIFO 淘汰：超出 10MB 丢头部
  let bytes = JSON.stringify(next).length;
  while (bytes > HISTORY_LIMIT_BYTES && next.length > 1) {
    next.shift();
    bytes = JSON.stringify(next).length;
  }
  await chrome.storage.session.set({ [key]: next });
}

export async function clearHistory(tabId: number): Promise<void> {
  await chrome.storage.session.remove(`msgs:${tabId}`);
}
