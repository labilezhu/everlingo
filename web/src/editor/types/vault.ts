export interface LangsResp {
  vaults: string[];
  count: number;
}

export interface Entry {
  name: string;
  path: string;
  type: 'dir' | 'file';
  children?: Entry[];
  /** 懒加载标记：整树重拉（刷新 / 切语言）后会被重置，已加载目录重新展开时会再次按需请求 */
  loaded?: boolean;
}

export interface TreeResp {
  path: string;
  depth: number;
  entries: Entry[];
}

export interface ReadResp {
  path: string;
  content: string;
  size_bytes: number;
}

export interface WriteResp {
  ok: boolean;
  path: string;
}

export interface MkdirResp {
  ok: boolean;
  path: string;
}

export interface DeleteResp {
  ok: boolean;
  path: string;
}

export interface RenameResp {
  ok: boolean;
  source: string;
  target: string;
}

// ── search ──

export type SearchMode = 'hybrid' | 'exact' | 'semantic';
export type TagsOp = 'and' | 'or';

export interface SearchReq {
  q?: string;
  mode?: SearchMode;
  kind?: string;
  item_type?: string;
  tags?: string[];
  tags_op?: TagsOp;
  limit?: number;
}

export interface SearchChunk {
  chunk_id: number;
  section_title: string;
  section_kind: string;
  char_offset: number;
  text: string;
}

export interface SearchHit {
  ulid: string;
  kind: 'item' | 'event';
  lang: string;
  item_type: string | null;
  file_path: string;
  title: string;
  score: number;
  source: string;
  chunk: SearchChunk | null;
  snippet: string;
}

export interface SearchResp {
  hits: SearchHit[];
  count: number;
  took_ms: number;
}

// ── tags ──

export interface TagCount {
  tag: string;
  count: number;
}

export interface TagsResp {
  tags: TagCount[];
  total: number;
}
