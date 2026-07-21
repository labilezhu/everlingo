import type { LangsResp, TreeResp, ReadResp } from '@/editor/types/vault';

const BASE = '/api/vault';

async function api<T>(
  url: string,
  init?: RequestInit,
): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (body.detail) detail = body.detail;
    } catch { /* fall through */ }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export function listLangs(): Promise<LangsResp> {
  return api<LangsResp>(`${BASE}/langs`);
}

export function tree(lang: string): Promise<TreeResp> {
  return api<TreeResp>(`${BASE}/${encodeURIComponent(lang)}/tree`);
}

export function read(lang: string, path: string): Promise<ReadResp> {
  return api<ReadResp>(
    `${BASE}/${encodeURIComponent(lang)}/read?path=${encodeURIComponent(path)}`,
  );
}

export function write(lang: string, path: string, content: string): Promise<{ ok: boolean; path: string }> {
  return api(
    `${BASE}/${encodeURIComponent(lang)}/write`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path, content }),
    },
  );
}
