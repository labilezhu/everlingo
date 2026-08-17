import type { LangsResp, TreeResp, ReadResp, SearchReq, SearchResp, TagsResp, MkdirResp, DeleteResp, RenameResp, ImageAsset } from '@/editor/types/vault';
import { apiFetch } from '@/services/apiFetch';

const BASE = '/api/vault';

/** 把 vault 相对路径编码为 URL 路径段（每段 encodeURIComponent）。 */
function encodeVaultRelPath(vaultRelPath: string): string {
  return vaultRelPath.split('/').map(encodeURIComponent).join('/');
}

/** markdown 图片预览绝对 URL（ADR 决策 3）：/api/vault/raw/{lang}/{vault_rel_path} */
export function assetUrl(lang: string, vaultRelPath: string): string {
  return `${BASE}/raw/${encodeURIComponent(lang)}/${encodeVaultRelPath(vaultRelPath)}`;
}

async function api<T>(
  url: string,
  init?: RequestInit,
): Promise<T> {
  // 401 由 apiFetch 统一兜底跳 /login
  const res = await apiFetch(url, init);
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

export function mkdir(lang: string, path: string): Promise<MkdirResp> {
  return api<MkdirResp>(
    `${BASE}/${encodeURIComponent(lang)}/mkdir`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path }),
    },
  );
}

export function deleteEntry(lang: string, path: string): Promise<DeleteResp> {
  return api<DeleteResp>(
    `${BASE}/${encodeURIComponent(lang)}/delete`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path }),
    },
  );
}

export function rename(lang: string, source: string, target: string): Promise<RenameResp> {
  return api<RenameResp>(
    `${BASE}/${encodeURIComponent(lang)}/rename`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source, target }),
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

/** 上传图片字节到 vault 内相对路径（PUT /raw/{lang}/{vault_rel_path}，multipart file=）。
 * 文件名 stem 为前端 scale 前算好的 src_resource_sha256；服务端仅做格式校验。 */
export function uploadImage(lang: string, vaultRelPath: string, file: Blob, mimeType: string): Promise<ImageAsset> {
  const form = new FormData();
  form.append('file', file, `image.${mimeType.split('/')[1] ?? 'bin'}`);
  return api<{ image: ImageAsset }>(
    `${BASE}/raw/${encodeURIComponent(lang)}/${encodeVaultRelPath(vaultRelPath)}`,
    { method: 'PUT', body: form },
  ).then(data => data.image);
}
