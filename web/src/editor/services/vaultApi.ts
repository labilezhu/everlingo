import type { LangsResp, TreeResp, ReadResp, SearchReq, SearchResp, TagsResp } from '@/editor/types/vault';

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

export function tree(lang: string, path: string = '', depth: number = 2): Promise<TreeResp> {
  const params = new URLSearchParams();
  if (path) params.set('path', path);
  params.set('depth', String(depth));
  return api<TreeResp>(`${BASE}/${encodeURIComponent(lang)}/tree?${params}`);
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

export function search(lang: string, body: SearchReq): Promise<SearchResp> {
  return api<SearchResp>(
    `${BASE}/${encodeURIComponent(lang)}/search`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    },
  );
}

export function listTags(lang: string, kind?: string, item_type?: string): Promise<TagsResp> {
  const params = new URLSearchParams();
  if (kind) params.set('kind', kind);
  if (item_type) params.set('item_type', item_type);
  const qs = params.toString();
  return api<TagsResp>(
    `${BASE}/${encodeURIComponent(lang)}/tags${qs ? '?' + qs : ''}`,
  );
}
