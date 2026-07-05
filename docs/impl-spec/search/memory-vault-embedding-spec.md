# Memory Vault 语义向量检索设计

为 [memory vault](/docs/impl-spec/worksplace/memory-vault-spec.md) 提供语义向量检索（chunk 级 KNN）与混合检索（FTS + 向量 RRF 融合）。全文检索见 [memory-vault-search-spec.md](./memory-vault-search-spec.md)（以下简称 FTS spec）。

## 目标与定位

- 复用 FTS spec 的 `chunks` 表（段级原文）、独立 indexer 进程、HTTP/UDS IPC、`protocol.py` 的 `SearchHit.source` / `chunk` 字段。
- 新增向量索引（sqlite-vec vec0）与 embedding 计算（OpenRouter text-embedding-3-small，经 `AIEmbedding`）。
- 查询三模式：`exact`（FTS spec）、`semantic`（本文）、`hybrid`（本文）。
- 嵌入在 indexer 进程内后台 worker 异步完成；未嵌入的 chunk 暂不参与向量召回（最终一致）。
- **per-lang DB**：FTS spec 的 per-lang SQLite DB 同样适用于向量层——每个 lang DB 各自维护 `chunk_embeddings` / `chunk_vec` / `meta`，各 lang DB 的 `meta.embedding_model_id` 与 `embedding_dim` 可不同。这为将来按语言选型 embedding 模型留出空间（如英文用 text-embedding-3-small、日文用 bge-m3-ja）。

## 与 FTS spec 的关系

| 复用项 | 出处 |
|---|---|
| `chunks` 表 DDL | FTS spec「Schema DDL」 |
| `chunk_embeddings` 表 DDL | FTS spec「Schema DDL」（本文管理其读写） |
| indexer 进程 / IPC / watchdog | FTS spec「进程拓扑」 |
| `protocol.py` SearchHit/ChunkRef/SearchRequest | FTS spec「查询 API」 |
| `sync.open_db` / `reconcile` | FTS spec「同步策略」 |
| `tokenizer.py` | FTS spec（向量侧不使用分词，但 hybrid 路径的 FTS 召回复用） |
| frontmatter 字段 chunk | FTS spec「Chunk 切分策略」：`headword`/`title`/`description`/`description_in_target_lang` 各生成一个 `section_kind='frontmatter'` 的 chunk，参与向量检索 |

## 技术选型

| 维度 | 选型 | 理由 |
|---|---|---|
| 向量库 | sqlite-vec（vec0 虚表） | vss 已停维，sqlite-vec 为继任者；与 `memory.sqlite` 同文件，零外部存储 |
| embedding 客户端 | `AIEmbedding`（langchain `OpenAIEmbeddings` 子类，经 OpenRouter） | `src/everlingo/mem/vault/search/embedding/ai_embedding.py` 既存；`embed_query` / `embed_documents` 协议 |
| embedding 模型 | text-embedding-3-small（1536 维） | 经 OpenRouter；可换，由 `meta.embedding_model_id` 标识 |
| 触发 | indexer 进程内后台守护线程 | 嵌入为 I/O 密集异步任务；复用 indexer 独占 SQLite |

>依赖增量：`sqlite-vec`（已批准）。CI 无额外安装步骤（wheel 自带扩展）。

## Schema 与扩展加载

### sqlite-vec 扩展加载

`sync.open_db()` 打开连接后加载扩展：

```python
import sqlite_vec
conn.enable_load_extension(True)
conn.load_extension(sqlite_vec.loadable_path())
conn.enable_load_extension(False)
```

加载失败 → log error，向量功能降级（FTS/`exact` 不受影响），`semantic`/`hybrid` 查询返回空 + warning。

### vec0 KNN 索引（动态建表）

dim 从 `meta.embedding_dim` 读取后动态建，故不在 schema.sql 静态写死：

```sql
CREATE VIRTUAL TABLE IF NOT EXISTS chunk_vec
USING vec0(chunk_id INTEGER PRIMARY KEY, embedding FLOAT[:dim])
```

`chunk_embeddings` 表（FTS spec 已定义）为权威持久存储；`chunk_vec` 为派生 KNN 索引，二者同步写入。

### meta 新增键

`meta` 表为 per-lang DB 独立（每 lang 一份），各 lang 可用不同 embedding 模型：

| key | 示例值 | 用途 |
|---|---|---|
| `embedding_model_id` | `openai/text-embedding-3-small:1536` | 换模型时作废旧 embedding + 重建 vec0；各 lang DB 可不同 |
| `embedding_dim` | `1536` | 动态建 vec0 虚表；各 lang DB 可不同 |
| `embedding_schema_version` | `1` | vec0 schema 变更时重建 |

## chunk_id 稳定化（前置改动）

`indexer.index_file`（FTS spec）在 `existing is not None` 分支开头比对 `content_hash`：未变则仅更新 `file_mtime`/`indexed_at`/`seen_count`/`last_seen`/`first_seen` 等元数据，**不删 chunks、不重建 FTS、不动 embedding**。

收益：watcher 触发 `touch`（mtime 变、内容不变）不再销毁 chunk_id → `chunk_embeddings` 行不失效 → 避免重复嵌入。元数据字段仍正常更新。

## 模块布局

```
src/everlingo/mem/vault/search/
  embedding/
    ai_embedding.py    # 既有：AIEmbedding（embed_query / embed_documents）
    worker.py          # 新增：EmbeddingWorker 后台线程，单 worker 轮询 N 个 lang DB
    store.py           # 新增：embedding 读写 + vec0 同步 + KNN 查询（per-lang conn）
  indexer.py           # 改：index_file 增 content_hash 短路；按 lang 路由 conn
  search.py            # 改：_vec_recall / _fuse / mode 路由；按 lang 取 conn
  sync.py              # 改：open_db 加载 sqlite-vec；对每个 lang reconcile 后启动 worker
  server.py            # 改：/status 增 per-lang embedding 计数；POST /{lang}/embed 端点
  cli.py               # 改：everlingo mem embed [LANG] 子命令
  protocol.py          # 改：StatusResponse 增 per-lang embedded_chunks / embedding_model_id
```

## Embedding worker

`embedding/worker.py`：单 worker 实例轮询 N 个 lang DB 的 pending chunks。

```python
class EmbeddingWorker:
    def __init__(self, conns: dict[str, Connection], embedders: dict[str, AIEmbedding], *, interval=2.0, batch=64): ...
        # conns: lang -> SQLite 连接（per-lang DB）
        # embedders: lang -> AIEmbedding（按该 lang DB 的 meta.embedding_model_id 创建；可为多 lang 共享同一 embedder 实例）
    def start(self) -> None     # 守护线程
    def stop(self) -> None
    def wake(self, lang: str | None = None) -> None  # watcher / index_file 后唤醒；lang=None 唤醒所有
```

- **触发时机**：indexer 启动对每个 lang reconcile 完成后 `start()` 补嵌存量；某 lang 的 `index_file` 写新 chunks 后 `wake(lang)`；某 lang `rebuild` 后全量重嵌该 lang。
- **轮询策略**：单线程按 lang 依次轮询，对每个 lang DB 执行 `SELECT chunk_id, text FROM chunks WHERE chunk_id NOT IN (SELECT chunk_id FROM chunk_embeddings WHERE model_id=:cur_model_id_of_lang) LIMIT :batch`，使用该 lang 对应的 embedder 嵌入，事务写回该 lang DB 的 `chunk_embeddings` + `chunk_vec`。单线程避免多 lang 并发争用同一 OpenRouter 客户端。
- **批量嵌入**：`embedder.embed_documents([text...])` → 事务写入 `chunk_embeddings` + `chunk_vec`。串行批次、串行 lang。
- **失败重试**：指数退避 3 次；失败 chunk 留待下轮。
- **降级**：某 lang 的 `AIEmbedding.create()` 抛 `ValueError`（未配 `OPENAI_EMBEDDING_MODEL`）→ 该 lang 的 worker 路径不启动，log info，向量功能对该 lang 关闭；其它 lang 不受影响。
- **content_hash 跳过**：由 chunk_id 稳定（content_hash 短路）保证，worker 不再算 hash。

## Embedding store

`embedding/store.py`（所有函数作用于传入的单个 lang DB conn，lang 由调用方提供）：

```python
def ensure_vec_table(conn, dim: int) -> None        # 建/重建该 lang DB 的 chunk_vec
def batch_upsert(conn, items, embedder) -> int      # 批量写该 lang DB 的 chunk_embeddings + chunk_vec
def knn(conn, query_vec, *, k, item_type, kind, tags) -> list[tuple[int, float]]
def rebuild_for_model(conn, new_model_id, dim) -> None # drop 该 lang DB 的 vec0 + 旧 embedding + 重建
```

- **过滤策略**：vec0 不支持复杂 WHERE。先取 `k * 3` 候选，再 join `chunks`+`documents` 按 item_type/kind/tags post-filter，取 top-k。无过滤时直接 top-k。lang 过滤已隐含于 DB，不再需要。
- **模型作废**：换某 lang 模型时对该 lang DB `DELETE FROM chunk_embeddings` + `DROP TABLE chunk_vec` + 用新 dim `ensure_vec_table` + 全量重嵌该 lang。其它 lang DB 不受影响。

## 查询路由

`search.py`（接收 `lang` 参数，路由到对应 lang DB 的 conn）：

```python
def search(query, lang, ..., mode='exact', limit=20) -> list[SearchHit]:
    conn = conns[lang]   # per-lang DB 连接
    if mode == 'exact':    return _fts_recall(conn, ...) # FTS spec
    if mode == 'semantic': return _vec_recall(conn, query, ..., limit)
    if mode == 'hybrid':   return _fuse(_fts_recall(conn, ...), _vec_recall(conn, ...), limit)
```

- **`_vec_recall`**：用该 lang 对应的 embedder `AIEmbedding.create(model_id=...).embed_query([query])` → `store.knn(conn, ...)` → join chunks + documents → `SearchHit(source='vec', lang=lang, chunk=ChunkRef, snippet=chunk.text[:N])`。
- **`_fuse`（RRF）**：两路各自按 score 排序；`score = Σ 1/(60 + rank_i)`；FTS 文件级 hit（无 chunk）按 ulid 去重，vec hit 按 (ulid, chunk_id) 去重；合并取 top-limit，`source='hybrid'`。RRF 在单 lang DB 内融合，不涉及跨 lang score 比较。
- item_type/kind/tags 过滤两路都应用。lang 已隐含于 DB，不再作为过滤参数。

## Search API
[Search API](/docs/impl-spec/search/memory-vault-search-spec.md) 中 “## Search API” 一节。

## CLI

- 新增 `everlingo mem embed [LANG] [--rebuild] [--status]`：经 HTTP `POST /{lang}/embed` 触发该 lang worker 跑一轮；`--rebuild` 先 drop 再全量重嵌该 lang；`--status` 报该 lang 的 embedded_chunks / total_chunks / model_id。LANG 省略时对所有 lang 依次执行。
- `GET /status` 响应增 per-lang `embedded_chunks`、`embedding_model_id`（聚合所有 lang DB）。

## 降级与边界

| 场景 | 行为 |
|---|---|
| 某 lang 的 `OPENAI_EMBEDDING_MODEL` 未配 | 该 lang worker 路径不启动；该 lang 的 `semantic`/`hybrid` 返回 `[]` + warning；该 lang 的 FTS / `exact` 正常；其它 lang 不受影响 |
| 某 lang DB 的 sqlite-vec 扩展加载失败 | indexer log error；该 lang 向量功能关闭；该 lang 的 FTS 正常；其它 lang 不受影响 |
| OpenRouter 调用失败 | worker 重试退避；失败 chunk 下轮再试；查询用已有 embedding 子集做 KNN |
| 某 lang 的 chunk 尚未嵌入 | 不参与该 lang 向量召回（最终一致）；该 lang hybrid 模式 FTS 路仍能命中 |
| 某 lang 换 embedding 模型 | 该 lang worker 检测 `model_id` 变化 → drop 该 lang vec0 + 旧 embedding → 新 dim 重建 → 全量重嵌该 lang；其它 lang 不受影响 |

## 测试策略

- `store.py`：fake embedder（确定性向量）测 upsert / knn / 模型作废 / 过滤（per-lang in-memory sqlite+vec）。
- `worker.py`：单 worker 轮询多 lang DB 的 pending 选择、批量、失败重试、wake 触发（fake embedder + 多个 in-memory sqlite+vec）。
- `indexer.test_index_file_content_hash_shortcircuit`：touch 未变内容，断言 chunk_id 不变、embedding 行不丢。
- `search.test_vec_recall_hybrid`：mock embedder，测 mode 路由、RRF 去重、source 字段、lang 路由到对应 conn。
- 集成：某 lang `rebuild` + worker → 断言该 lang embedded_chunks == 该 lang chunks 总数。

## 与现有架构的契合

- 复用 FTS spec 的 indexer 进程、IPC、protocol；不引入外部存储。
- gateway 进程不加载 embedder、不打开 SQLite、不碰 vec0。
- `chunks.text` 保留原文（不分词），向量侧直接用；FTS 侧分词另存 FTS 列，互不干扰。