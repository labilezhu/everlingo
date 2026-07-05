-- ref: docs/impl-spec/search/memory-vault-search-spec.md — Schema DDL
-- memory vault search schema (SQLite + FTS5)
-- 每个目标学习语言独立一份 DB（$workspace/memory/languages/$lang/index/memory.sqlite）。
-- lang 已隐含于 DB，不作为 documents 列存储。
-- - documents: file-level 元数据 + body
-- - documents_fts: 字段化 FTS5 索引（unicode61 + Python 预分词）
-- - chunks: 段级文本（向量作用层）
-- - chunk_embeddings: 嵌入表（embedding worker 管理读写）
-- - meta: 分词器版本 / schema 版本 / embedding 模型配置

CREATE TABLE documents (
  rowid INTEGER PRIMARY KEY,
  ulid TEXT UNIQUE,                       -- kb item 的 ulid；event 用合成键 'event:{lang}:{date}'
  kind TEXT NOT NULL,                     -- 'item' | 'event'
  item_type TEXT,                         -- vocab/phrase/grammar/pragmatics/others；event 为 NULL
  file_path TEXT NOT NULL UNIQUE,         -- 相对 $workspace/memory/languages/$lang/vault 的路径
  slug TEXT,
  headword TEXT,
  title TEXT,
  description TEXT,
  description_in_target_lang TEXT,
  aliases TEXT,
  related TEXT,
  tags TEXT,
  first_seen TEXT,
  last_seen TEXT,
  seen_count INTEGER,
  schema_version INTEGER,
  body TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  file_mtime TEXT NOT NULL,
  indexed_at TEXT NOT NULL
);
CREATE INDEX idx_doc_type ON documents(item_type);
CREATE INDEX idx_doc_kind ON documents(kind);

CREATE VIRTUAL TABLE documents_fts USING fts5(
  headword,
  title,
  description,
  description_in_target_lang,
  aliases,
  related,
  tags,
  body,
  body_raw UNINDEXED,
  tokenize='unicode61'
);

CREATE TABLE chunks (
  chunk_id INTEGER PRIMARY KEY,
  doc_rowid INTEGER NOT NULL REFERENCES documents(rowid) ON DELETE CASCADE,
  chunk_index INTEGER NOT NULL,
  section_title TEXT,
  section_kind TEXT,
  text TEXT NOT NULL,
  char_offset INTEGER,
  content_hash TEXT NOT NULL,
  UNIQUE(doc_rowid, chunk_index)
);
CREATE INDEX idx_chunks_doc ON chunks(doc_rowid);

CREATE TABLE chunk_embeddings (
  chunk_id INTEGER PRIMARY KEY REFERENCES chunks(chunk_id) ON DELETE CASCADE,
  model_id TEXT NOT NULL,
  dim INTEGER NOT NULL,
  embedding BLOB NOT NULL,
  embedded_at TEXT NOT NULL
);

-- vec0 KNN 索引 dim 由 indexer 启动时按 meta 动态建（ensure_vec_table）。
-- vec0 与 chunk_embeddings 的同步清理在 embedding/store.py 的 sync_* 函数里
-- 集中处理（避免 chunk_vec 表未建时触发器失败）。

CREATE TABLE meta (
  key TEXT PRIMARY KEY,
  value TEXT
);
