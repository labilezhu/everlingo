# Memory Vault 全文搜索设计

基于 SQLite + FTS5 为 [memory vault](/docs/impl-spec/worksplace/memory-vault-spec.md) 提供全文检索。语义向量检索（embedding + KNN）与混合检索另见 [memory-vault-embedding-spec.md](./memory-vault-embedding-spec.md)。

## 目标与定位

- 对 `$workspace/memory/` 下的 markdown vault 提供全文检索。
- 索引对象分三类：
  - **kb items**（`$lang/items/{type}/{slug}--{ulid}.md`）：字段化最强，主要检索对象。
  - **events**（`$lang/events/YYYY/MM/YYYY-MM-DD.md`）：按天聚合的多事件文件，次要检索对象。
  - `USER.md`：单文件、短文本、Agent 频繁重写，优先级最低。
- 全文检索（FTS）≠ 语义检索。本文仅覆盖 FTS；语义检索见上。

## 技术选型

| 维度 | 选型 | 理由 |
|---|---|---|
| 引擎 | SQLite + FTS5 | Python 标准库 `sqlite3` 在 3.11 自带 SQLite 通常已编译 FTS5；零外部存储服务 |
| 分词 | jieba（中文）+ fugashi+mecab/unidic（日文），按 Unicode 脚本分发 | FTS5 内置 `trigram` 对 CJK 无词边界、英文精确匹配偏差；改用 unicode61 + Python 预分词 |
| FTS 模式 | 非 external content，自管 insert/delete | 自定义分词需把分词后文本直接喂入 FTS5 列，不能用 `content='documents'` 外部引用原文 |
| 文件监听 | watchdog | 跨平台 inotify/FSEvents/ReadDirectoryChanges 封装，实时事件 |
| IPC | HTTP/1.1 over unix domain socket，REST + JSON | 支持 curl 调试，复用 fastapi/uvicorn 的 unix socket 能力，零新 server 依赖 |
| 向量库（将来） | sqlite-vec | vss 已停维，sqlite-vec 为继任者；落地时再批准 |
| embedding 模型（将来） | 多语言模型（如 bge-m3 类） | 覆盖 en/ja/zh；落地时再选型 |

## 进程拓扑

采用**独立 indexer 进程**方案（方案 A）。SQLite 文件只有 indexer 进程以读写方式打开；gateway 与 CLI 均为 indexer 的 HTTP 客户端，不直接触碰 SQLite。

indexer 以**前台进程**方式运行（`everlingo mem indexer start` 阻塞当前终端，Ctrl-C 退出），日志写 `$workspace/logs/indexer.log`。如需后台运行，由用户自行 `nohup everlingo mem indexer start &` 或纳入 systemd 等进程管理。

```
┌─────────────────────────┐     HTTP over unix socket   ┌──────────────────────────┐
│  Gateway 进程（可多个）  │  ─── $workspace/  ──────►  │  Indexer 进程（单例前台） │
│  - Chat Agent           │     index/indexer.sock     │  - SQLite RW (WAL)        │
│  - Memory Writer Agent  │                            │  - watchdog watcher       │
│  - SearchClient (thin)  │  ◄── SearchHit JSON ─────  │  - 启动对账 + embedding  │
│  不碰 SQLite            │                            │  - tokenizer(jieba+mecab) │
│  不加载 mecab/jieba     │                            │  - FastAPI server         │
│  不加载 embedder        │                            │  - embedding worker       │
└─────────────────────────┘                            │    (见 embedding-spec)   │
                                                       └──────────────────────────┘
                                                                 │
                                                                 ▼
                                                        $workspace/index/memory.sqlite
```

### 为什么独立进程

- **多 gateway 实例写冲突**：`gateway.md` 支持同时跑 `--channel_wechat`、`--channel_web`、`--channel_stdio`，是不同进程。若每个进程都带 watcher 写同一份 `memory.sqlite`，SQLite 单写者锁会冲突。独立 indexer 进程独占写，彻底解决。
- **mecab/jieba 常驻内存**：unidic 词典 + mecab 约几十 MB 常驻，每个 gateway 进程都加载一份浪费且拖慢启动。独立进程只加载一次。
- **重索引/重建不影响聊天**：分词器升级全量重建时，gateway 不停。
- **embedding worker 更重**：调 LLM 嵌入天然适合独立进程（见 embedding-spec）。
- **查询也走 IPC**：相比 LLM 调用（数百 ms），本机 unix socket HTTP 往返（sub-ms ~ 几 ms）可忽略。
- **前台进程，用户自管后台化**：indexer 默认前台阻塞运行，日志落 `$workspace/logs/indexer.log`，Ctrl-C 退出。需常驻时由用户 `nohup ... &` 或纳入 systemd；不内置 daemon 化，保持工具行为简单可预期。

### gateway 降级行为

indexer 进程不可达时：
- `SearchClient.search()` 返回空列表 + log warning，Chat Agent 继续跑（无检索增强，聊天不中断）。
- Writer 投递的 `index_file` 请求丢弃（fire-and-forget），靠 watcher 兜底 + indexer 重启后启动对账补漏。

## 模块布局

```
src/everlingo/mem/vault/search/
  __init__.py
  schema.sql         # 建表 DDL
  tokenizer.py       # Unicode 脚本分发 + jieba/mecab 封装；tokenize(text)->str；记录 tokenizer_version
  indexer.py         # 解析 .md -> 写 documents + documents_fts + chunks；content_hash 短路（见 embedding-spec）
  search.py          # indexer 进程内直接查 SQLite；query 先 tokenize 再 MATCH
  sync.py            # 全量对账 + content_hash diff + 分词器版本比对
  watcher.py         # watchdog 事件监听（indexer 进程内），300ms 去抖，ulid 幂等 upsert
  events_index.py    # events 文件解析（FTS 整文件一行，chunks 按 ## Event 拆）
  server.py           # FastAPI app + uvicorn 入口（everlingo mem indexer start）
  protocol.py         # pydantic 请求/响应模型（SearchHit/ChunkRef 序列化）
  client.py           # gateway 侧 SearchClient（httpx + unix socket）
  cli.py              # 命令行索引维护工具（经 HTTP 委托 indexer 服务）
```

- gateway 进程只依赖 `client.py` + `protocol.py`，不加载 mecab/jieba/embedder，不打开 SQLite。
- indexer 进程加载全部模块，独占 SQLite 读写 + watchdog + embedding worker。见 [embedding-spec](/docs/impl-spec/search/memory-vault-embedding-spec.md)。

## DB 文件位置

所有路径基于当前 workspace 解析（见 [workspace.md](/docs/impl-spec/worksplace/workspace.md)「Workspace 选择机制」）：

| 用途 | 路径 |
|---|---|
| DB | `$workspace/index/memory.sqlite` |
| 监听根 | `$workspace/memory/`（仅 `.md`） |
| IPC socket | `$workspace/index/indexer.sock` |

- DB 与 vault 同 workspace 根、与用户内容分离，便于备份
- 只有 indexer 进程以读写方式打开 SQLite；gateway 与 CLI 永不直接打开
- 每个 workspace 一个独立 indexer 实例（独立 socket/DB），不可跨 workspace。同一台机跑多 workspace 时各起一个 `everlingo mem indexer start` 进程
- gateway 与 indexer 必须解析到同一 workspace，否则 `SearchClient` 连不上对应 socket

## Schema DDL

```sql
-- 文件级元数据 + 全文，FTS 作用层
CREATE TABLE documents (
  rowid INTEGER PRIMARY KEY,
  ulid TEXT UNIQUE,                       -- kb item 的 ulid；event 用合成键 'event:{lang}:{date}'
  kind TEXT NOT NULL,                     -- 'item' | 'event' | 'user'
  lang TEXT,                              -- en / ja / ...
  item_type TEXT,                         -- vocab/phrase/grammar/pragmatics/others；event/user 为 NULL
  file_path TEXT NOT NULL UNIQUE,         -- 相对 $workspace/memory 的路径
  slug TEXT,
  headword TEXT,
  title TEXT,
  intro_in_interface_lang TEXT,
  intro_in_target_lang TEXT,
  aliases TEXT,                           -- '\n' 连接
  related TEXT,                           -- '\n' 连接
  tags TEXT,                              -- ' ' 连接，便于过滤
  first_seen TEXT,
  last_seen TEXT,
  seen_count INTEGER,
  schema_version INTEGER,
  body TEXT NOT NULL,                     -- frontmatter 后的 markdown 原文，供 chunks 切分/展示/content_hash
  content_hash TEXT NOT NULL,            -- 整文件 hash（基于原文），跳过未变更的重嵌入与重索引
  file_mtime TEXT NOT NULL,               -- ISO 字符串，watcher 去抖与对账依据
  indexed_at TEXT NOT NULL
);
CREATE INDEX idx_doc_lang_type ON documents(lang, item_type);
CREATE INDEX idx_doc_kind ON documents(kind);

-- 全文索引：字段化，便于按字段加权与高亮
-- 各列存「分词后空格连接」文本；body_raw 存原文供 snippet() 干净高亮
CREATE VIRTUAL TABLE documents_fts USING fts5(
  headword, title,
  intro_in_interface_lang, intro_in_target_lang,
  aliases, related, tags, body,
  body_raw UNINDEXED,                     -- 原文，仅给 snippet() 用，不索引
  tokenize='unicode61'
);

-- 段级文本，向量作用层
CREATE TABLE chunks (
  chunk_id INTEGER PRIMARY KEY,
  doc_rowid INTEGER NOT NULL REFERENCES documents(rowid) ON DELETE CASCADE,
  chunk_index INTEGER NOT NULL,
  section_title TEXT,                     -- '## 例句' / '## Event' / NULL
  section_kind TEXT,                      -- 'event'|'explanation'|'example'|'memory_hook'|...
  text TEXT NOT NULL,                     -- 该段清洗后纯文本（原文，不分词）
  char_offset INTEGER,                    -- 在 body 中的起点，用于命中后定位/滚动
  content_hash TEXT NOT NULL,             -- 段 hash（基于原文），跳过未变更段的重嵌入
  UNIQUE(doc_rowid, chunk_index)
);
CREATE INDEX idx_chunks_doc ON chunks(doc_rowid);

-- 嵌入表（由 [embedding-spec](./memory-vault-embedding-spec.md) 管理读写与 vec0 索引）
CREATE TABLE chunk_embeddings (
  chunk_id INTEGER PRIMARY KEY REFERENCES chunks(chunk_id) ON DELETE CASCADE,
  model_id TEXT NOT NULL,                 -- 'bge-m3:1024' 等，换模型时按此作废
  dim INTEGER NOT NULL,
  embedding BLOB NOT NULL,
  embedded_at TEXT NOT NULL
);

-- 元信息：分词器版本、schema 版本，启动时比对触发重建
CREATE TABLE meta (
  key TEXT PRIMARY KEY,
  value TEXT
);
-- 记录示例：
--   tokenizer_version = 'jieba:0.42+fugashi:1.1+unidic:2024...'
--   schema_version    = '1'
```

### events 文件特殊处理

events 文件含多个 `## Event` 段。FTS 与 chunks 两层粒度解耦：

- **FTS 层**：整文件一行入库，`kind='event'`，`ulid` 用合成键 `event:{lang}:{date}`（如 `event:ja:2026-06-26`）。
- **chunks 层**：按 `## Event` 拆成多行，每行 `section_kind='event'`，获得语义粒度，供将来向量检索。

## Tokenizer 规范

### frontmatter 容错解析

vault 的 `.md` frontmatter 实际由 LLM Writer（mem_writer_agent）按 `kb_items_spec.md` 模板手写。LLM 偶尔产出近似 YAML（内嵌引号 / 冒号），严格 `yaml.safe_load` 会失败。indexer 与 writer 共用 `src/everlingo/mem/vault/frontmatter.py`：

- `tolerant_parse`：先 `yaml.safe_load`，失败回退逐行 `key: value` 解析；已知 list 字段（`aliases`/`related`/`tags`）空值归一为 `[]`；`seen_count`/`schema_version` 转 int。
- `parse_frontmatter`：拆 raw frontmatter + body 后调 `tolerant_parse`。
- `normalize_frontmatter_text`：用 `tolerant_parse` 取字段后 `yaml.safe_dump`（`sort_keys=False` / `default_flow_style=False` / `width=4096`）重序列化，保证落盘 frontmatter 永远合法。`mem_write_file` 写盘前调用，body 段字节不变。

### 分词调度（按 Unicode 脚本分发）

单文件常含界面语言（zh）+ 目标语言（en/ja）混排，单 tokenizer 处理不了。按 Unicode 脚本分段分发，不依赖语言检测器：

```
tokenize(text):
  扫描字符，按脚本分段:
    Latin        -> 保留原文，小写化（unicode61 后续按空白切）
    Han          -> jieba.cut
    Hiragana/Katakana/Kanji -> mecab.parse (fugashi + unidic)
  合并所有 token，空格连接成字符串
```

- `intro_in_target_lang` 等纯单语字段也走同一调度器（脚本能正确分发，无需按字段特殊处理）。
- 词典选型：**unidic**（粒度细、现代项目主流）。
- 仅 indexer 进程加载 tokenizer；gateway 不加载。

### 查询侧必须同样分词

`search()` 收到 query 后，**先用同一 `tokenize()` 处理 query 串**再拼 `MATCH` 表达式，否则索引侧分词、查询侧未分词，匹配不上。这是与 trigram 方案最大的行为差异。分词在 indexer 进程内执行，gateway 侧透明。

### 词边界行为

unicode61 + 预分词后，FTS5 默认整 token 匹配："computer" 不再命中 "computers"。解决之前 trigram 的词边界问题。

### snippet 干净原文

FTS5 的 `snippet()` 作用于 `body_raw` UNINDEXED 列，返回**干净原文**（无多余空格）。代价是 FTS 表多存一份原文（与 `documents.body` 重复一次，可接受）。

### 分词器版本与重索引

jieba 词典更新、unidic 版本变化会导致 token 集变化，需触发重索引。`meta` 表记录 `tokenizer_version`，indexer 启动时比对，版本变化则全量重建 FTS（FTS 重建便宜，毫秒级，不像 embedding）。

`content_hash` 基于**原文**算（不随分词器版本变），保证重索引时能跳过未变文件的解析，只重算分词。

## Chunk 切分策略

- 按 markdown AST 遍历 `##` section，每段一 chunk。
- `section_title` / `section_kind` 从标题识别：
  - events 的 `## Event` → `section_kind='event'`
  - kb item 的 `## 例句` → `'example'`
  - `## 给我的解释` → `'explanation'`
  - `## 记忆钩子` → `'memory_hook'`
  - 等等
- 单 chunk 超阈值 **800 字符**时按段落/句号二次切，子 chunk 继承 `section_title`。
- `char_offset` 记 body 内起点，命中后用于前端滚动定位；frontmatter chunk 的 `char_offset` 为 `NULL`（不在 body 内）。
- `chunks.text` 保留**原文**（向量嵌入用原文，不分词），不受分词器版本影响。
- **frontmatter 字段 chunk**（仅 `kind='item'`）：`headword` / `title` / `intro_in_interface_lang` / `intro_in_target_lang` 四个文本内容字段各生成一个 chunk，`section_kind='frontmatter'`，`section_title=<字段名>`，`text` 格式为 `"{key}: {value}"`，`chunk_index` 排在 body chunk 之前。数组字段（`aliases`/`related`/`tags`）不生成 chunk。详见 `indexer.py` `_frontmatter_chunks`。

## Search API

HTTP/1.1 over unix domain socket，REST + JSON。uvicorn 绑定 `$workspace/index/indexer.sock`，FastAPI 提供路由与 pydantic 模型校验，自带 `/docs` 交互文档便于浏览器调试。

### Search API Spec
[Search API Spec](/docs/impl-spec/search/search-api-spec.md)


### 实现

- indexer 进程：FastAPI app + uvicorn `--uds $workspace/index/indexer.sock`。SearchHit/ChunkRef 用 pydantic 模型，序列化自动完成。
- gateway 进程：`SearchClient`（httpx，unix socket transport），持久连接 + 自动重连。
- 协议层零新设计：复用 fastapi/uvicorn（已在依赖）+ httpx（新增）。

## 同步策略

### 主路径：watchdog watcher（indexer 进程内）

watchdog 监听 `$workspace/memory/` 下的 `.md` 增删改，事件路由到 indexer：

| 事件 | 动作 |
|---|---|
| 文件新建 | 解析 → insert documents + FTS + chunks |
| 文件修改 | 比对 `file_mtime` → upsert（按 `ulid`/合成键） |
| 文件重命名 | `ulid` 不变则只更新 `file_path`；`ulid` 变化视为删除旧 + 新建 |
| 文件删除 | 按 `file_path` 查到行后删 documents + FTS + chunks（CASCADE） |

- **去抖**：编辑器常触发多次 write 事件，watcher 内做 300ms 去抖再索引。
- **幂等**：indexer 按 `ulid` 幂等 upsert，重复触发无副作用。

### 快路径：Writer 经 HTTP 投递

`Memory Writer Agent` 写完 `.md` 后，经 `SearchClient` 向 indexer 发 `POST /index` 请求，**fire-and-forget**（失败靠 watcher + indexer 重启后启动对账兜底）。gateway 进程不直接调 indexer.py，不打开 SQLite。

### 启动时全量对账（indexer 进程内）

indexer 进程启动先扫一遍 vault，用 `file_mtime` 与 `content_hash` 对账（补漏 + 清孤儿行），再启动 watcher。覆盖 watcher 漏掉的事件（如 indexer 未运行期间的外部编辑）。同时比对 `meta.tokenizer_version`，版本变化则全量重建 FTS。

### 数据流

```
Writer 写 .md ─► SearchClient.index_file(path) ─HTTP─► indexer /index
                                                              │
                                                  indexer 进程 ├─► documents + documents_fts (文件级)
                                                              │     └─ 切 section ──► chunks (段级, 无 embedding)
                                                              │
                                                  watchdog watcher (兜底, mtime 去抖, ulid 幂等 upsert)
                                                              │
indexer 启动 ─► 全量对账 (scan + content_hash diff + tokenizer 版本比对) ─► 启动 watcher
# embedding worker 数据流见 embedding-spec
```

## 查询 API

### 返回类型（protocol.py 中定义，供 gateway 与 indexer 共享）

```python
@dataclass
class ChunkRef:
    chunk_id: int
    section_title: str | None
    section_kind: str | None
    char_offset: int
    text: str

@dataclass
class SearchHit:
    ulid: str
    kind: str
    lang: str | None
    item_type: str | None
    file_path: str
    title: str | None
    score: float
    source: Literal['fts', 'vec', 'hybrid']   # 'vec'/'hybrid' 由 embedding-spec 产出
    chunk: ChunkRef | None                     # 段级命中时填，文件级 FTS 命中为 None
    snippet: str                               # FTS snippet() 或 chunk.text 片段
```

### gateway 侧接口（client.py）

```python
class SearchClient:
    def __init__(self, uds_path: str): ...
    def search(self, query: str, *, lang=None, item_type=None,
               tags=None, kind=None,
               mode: Literal['exact','semantic','hybrid'] = 'exact',  # semantic/hybrid 见 embedding-spec
               limit: int = 20) -> list[SearchHit]: ...
    def index_file(self, path: str) -> bool: ...   # fire-and-forget
    def status(self) -> dict: ...
```

- indexer 不可达时 `search()` 返回 `[]` + log warning；`index_file()` 返回 `False` + log warning。

### indexer 侧接口（search.py，进程内直接查 SQLite）

```python
def search(
    query: str,
    lang: str | None = None,
    item_type: str | None = None,
    tags: list[str] | None = None,
    kind: str | None = None,
    mode: Literal['exact', 'semantic', 'hybrid'] = 'exact',  # semantic/hybrid 见 embedding-spec
    limit: int = 20,
) -> list[SearchHit]: ...
```

### 查询示例：找含 "computer" 的短语

```sql
SELECT d.ulid, d.slug, d.headword, d.title,
       snippet(documents_fts, 8, '【', '】', '…', 12) AS body_snippet
FROM documents_fts f
JOIN documents d ON d.rowid = f.rowid
WHERE documents_fts MATCH :tokenized_query
  AND d.kind = 'item'
  AND d.item_type = 'phrase'
ORDER BY rank
LIMIT 20;
```

- `:tokenized_query` 为 query 经 `tokenize()` 处理后的字符串
- `snippet(documents_fts, 8, ...)`：第 8 列即 `body_raw`（UNINDEXED），返回干净原文高亮片段
- `d.item_type='phrase'`：范围限定到短语类知识点
- `ORDER BY rank`：bm25 加权排序，默认各列权重 1.0；如要 headword/title 权重更高，改用 `bm25(documents_fts, 10.0, 10.0, 4.0, 4.0, 2.0, 2.0, 2.0, 1.0, 0.0)`

### 仅正文命中

FTS5 列限定语法：

```sql
WHERE documents_fts MATCH 'body : computer'
  AND d.kind = 'item'
  AND d.item_type = 'phrase'
```

### 多词 / 短语

- `"take for granted"`：短语匹配
- `computer OR software`
- `computer AND science`（默认 AND，可省略）

### mode 路由

- `mode='exact'`：走 FTS（精确词查询，unicode61 + 预分词整 token 匹配）
- `mode='semantic'` / `mode='hybrid'`：见 [embedding-spec](./memory-vault-embedding-spec.md)

`exact` 接口与返回类型与后两者一致，避免破坏性变更。

## 索引维护 CLI

一次性手动维护工具，**全部经 HTTP 委托 indexer 服务**，不直接打开 SQLite。与常驻 watchdog watcher 共享 `indexer.index_file()` 与 `sync.reconcile()` 同一入口，行为一致。

### 命令

```bash
# 启动 indexer 进程（前台阻塞）
everlingo mem indexer start

# 查询 indexer 状态（GET /status）
everlingo mem indexer status

# 增量刷新：扫描指定文件或目录，按 mtime + content_hash upsert/skip
everlingo mem reindex [PATH]              # PATH 为文件或目录；省略则全 vault

# 完全删除 index 数据，从零重建
everlingo mem reindex --rebuild

# Workspace 选择（与 gateway 入口一致，见 workspace.md「Workspace 选择机制」）
--workspace-dir <path>                    # 直接指定 workspace 根目录（与 -w 互斥）
-w, --workspace NAME                      # 指定 ~/.everlingo/workspaces/ 下的名字
# 环境变量：EVERLINGO_WORKSPACE_DIR / EVERLINGO_WORKSPACE
# 默认：default
#
# indexer 进程据此解析监听根 / DB 路径 / socket 路径（见「DB 文件位置」章节）
# gateway 与 CLI 必须用同一 workspace，否则连不上对应 socket

# 其它选项
-v, --verbose                             # 逐文件输出
--dry-run                                 # 只报告将做什么，不写库（经 indexer 实现）
```

### 行为定义

| 命令 | 行为 |
|---|---|
| `indexer start` | 前台启动 indexer 进程（FastAPI + uvicorn `--uds`），独占 SQLite RW，跑 watcher + 启动对账；阻塞当前终端，日志写 `$workspace/logs/indexer.log`，Ctrl-C 退出。 |
| `indexer status` | 经 `GET /status` 查询运行状态、文档数、chunk 数、tokenizer 版本。 |
| `reindex [PATH]` | 经 `POST /index` 批量投递 PATH 下 `.md`，由 indexer 比对 `file_mtime`+`content_hash`：未变 skip，已变 upsert，清孤儿。PATH 省略 = 全 vault。 |
| `reindex --rebuild` | 经 `POST /rebuild`，indexer 删除 DB 文件 → 重新 init schema → 全量扫描重建。 |

### 前置检查

`reindex` 与 `reindex --rebuild` 执行前先 `GET /status` 探测 indexer 服务是否在线：
- 在线：继续执行。
- 不在线：报错退出，提示先 `everlingo mem indexer start`。

### 退出码

- `0` 成功
- 非 `0` 失败（indexer 未在线、IO 错误、schema 初始化失败等）

### 实现要点

- 新增 `src/everlingo/mem/vault/search/cli.py`：`indexer` 与 `reindex` 子命令实现，经 HTTP 调用 indexer 服务。
- `main.py` 改造为 argparse subparsers：`everlingo mem ...` 与将来的 `everlingo gateway ...`（原默认行为）并存。向后兼容：无子命令时保持当前 gateway stdio 行为。
- CLI 与 gateway 共享 `client.py` 的 `SearchClient`，单一代码路径，无本地直连分支。

### 与 watcher 的关系

- CLI 是**一次性手动维护工具**；watcher 是**常驻自动同步**。两者共享同一 indexer/sync 入口，行为一致。
- CLI 适用于：首次构建、外部编辑后补漏、分词器升级后重建、排查索引不一致。

## 语义向量检索与混合检索

见 [memory-vault-embedding-spec.md](./memory-vault-embedding-spec.md)：sqlite-vec 向量索引、embedding worker、`mode='semantic'`（chunk 级 KNN）、`mode='hybrid'`（FTS + 向量 RRF 融合）。

## 依赖增量

### 本期

- `watchdog`：文件系统监听（indexer 进程用）
- `jieba`：中文分词，纯 pip，无系统依赖（indexer 进程用）
- `fugashi` + `unidic`：日文分词（indexer 进程用）
  - fugashi 的 wheel 捆绑 mecab 库，无需 apt install mecab
  - unidic pip 包提供词典，首次需 `python -m unidic download`（联网下载 ~50MB）
- `httpx`：gateway 侧 SearchClient HTTP 客户端（unix socket transport）

> 注：`fastapi` + `uvicorn` 已在 `pyproject.toml` 依赖中，indexer server 直接复用，无新增。
> jieba/fugashi/unidic/watchdog 在 `pyproject.toml` 列为依赖，但仅 indexer 进程运行时加载；gateway 进程不加载。

### CI 要求

- 安装步骤加 `python -m unidic download`

> `sqlite-vec` 与 embedding 客户端依赖见 [embedding-spec](./memory-vault-embedding-spec.md)。

## 与现有架构的契合

- 位于 `mem/vault/` 子树，归属 memory 域，与 `mem_writer_agent.py` 同层。
- 不改 ARCHITECTURE.md 主流水线（Chat Agent → Extract → Writer），只在 Writer 之后挂一个「经 HTTP 投递索引请求」步骤。
- gateway 多实例（wechat/web/stdio）并存时无 SQLite 写冲突——全是 indexer 的 HTTP 客户端。
- 不引入外部存储服务（无 Elasticsearch / tantivy），契合「单体 python 程序」定位；indexer 为同一 python 包内的前台子命令，由用户自管后台化（nohup / systemd）。

## 扩展位

- `documents` 表 / `chunks` 表的 `content_hash` 基于**原文**算，分词器换版本只重算 FTS，不重嵌向量。
- 分词器抽象为 `Tokenizer` 接口，默认 jieba+mecab 脚本分发，将来可换。
- `chunk_embeddings.model_id` 多模型/作废机制由 [embedding-spec](./memory-vault-embedding-spec.md) 管理。
- `SearchHit.source` / `chunk` 字段由 embedding-spec 落地使用。
- IPC 协议为 REST/JSON，新增端点即可扩展（如 `/health`、`/stats`、向量检索端点）。
