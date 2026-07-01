-- ref: docs/impl-spec/search/memory-vault-search-spec.md — Schema DDL
-- memory vault search schema (SQLite + FTS5)
-- - documents: file-level 元数据 + body
-- - documents_fts: 字段化 FTS5 索引（unicode61 + Python 预分词）
-- - chunks: 段级文本（向量作用层，本期建表不写 embedding）
-- - chunk_embeddings: 嵌入表（本期建表不写数据）
-- - meta: 分词器版本 / schema 版本

CREATE TABLE documents (
  rowid INTEGER PRIMARY KEY,
  ulid TEXT UNIQUE,
  kind TEXT NOT NULL,
  lang TEXT,
  item_type TEXT,
  file_path TEXT NOT NULL UNIQUE,
  slug TEXT,
  headword TEXT,
  title TEXT,
  intro_in_interface_lang TEXT,
  intro_in_target_lang TEXT,
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
CREATE INDEX idx_doc_lang_type ON documents(lang, item_type);
CREATE INDEX idx_doc_kind ON documents(kind);

CREATE VIRTUAL TABLE documents_fts USING fts5(
  headword,
  title,
  intro_in_interface_lang,
  intro_in_target_lang,
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

CREATE TABLE meta (
  key TEXT PRIMARY KEY,
  value TEXT
);
