# Search API spec

搜索 Memory Vault 记忆知识库。支持全文精确搜索、语义搜索、混合搜索。

IPC socket 路径：`$workspace/indexer.sock`（workspace 级共享，不随 lang 拆分）。

## REST 端点

| 方法 路径 | 用途 | 请求 body | 响应 |
|---|---|---|---|
| `POST /{lang}/search` | 全文/语义/混合检索该 lang vault | `{q, item_type?, tags?, kind?, mode, limit}` | `{hits:[...], count, took_ms}` |
| `POST /{lang}/index` | Writer 投递该 lang vault 的索引请求 | `{path}` | `{ok}` |
| `POST /{lang}/delete` | 删除该 lang vault 中指定文件索引 | `{path}` | `{ok}` |
| `POST /{lang}/rebuild` | 全量重建该 lang DB | `{}` | `{ok, indexed, chunks, took_ms}` |
| `POST /{lang}/embed` | 触发该 lang embedding worker 跑一轮（见 [embedding-spec](/docs/impl-spec/search/memory-vault-embedding-spec.md)） | `{rebuild?}` | `{ok, embedded}` |
| `GET /status` | 查询 indexer 状态（聚合所有 lang DB） | — | `{running, langs:[{lang, tokenizer_version, docs, chunks, embedded_chunks, embedding_model_id}], uptime_s}` |

注：
- `lang` 为目标学习语言编码（en/ja/...），作为 path segment 的第一段。indexer 启动时按 `$workspace/memory/languages/*/` 确定可用 lang 集合，请求 lang 不在集合内返回 404 / 错误。
- `GET /status` 不带 lang（workspace 级聚合），返回各 lang DB 的状态列表。

### POST /{lang}/search
搜索指定 lang 的 vault

#### Request path
- `lang`：目标学习语言编码（必填）。如 `en`、`ja`、`zh-CN`。

#### Request body
Request: {q, item_type?, tags?, kind?, mode, limit}

字段说明：

q: 要搜索的文本或语义
kind:       匹配过滤条件：memory vault 文档分类。取值包括： 
    item : 知识类文档
    event ： 事件类文档
item_type:  匹配过滤条件：知识类型 。取值包括： 
    kind=item 时，取值包括： vocab/phrase/grammar/pragmatics/others
    kind=event 为 NULL
mode: 搜索模式。一般情况下，优先使用 hybrid 混合搜索： `"mode":"hybrid"`。取值包括： 
    exact ： 全文精确搜索
    semantic ： 语义搜索
    hybrid ： 混合搜索。混合以上两人种搜索的结果
limit: 搜索返回结果数限制


#### curl 示例

```bash
# 搜索含 "god" mode: hybrid
curl --unix-socket $workspace/indexer.sock http://localhost/en/search \
  -H 'Content-Type: application/json' \
  -d '{"q":"god","mode":"hybrid","limit":4}' | jq -r 
```

#### Response body


##### 示例 1 - 全文搜索含 "god" 的词语
```bash
curl --unix-socket $workspace/indexer.sock http://localhost/en/search \
  -H 'Content-Type: application/json' \
  -d '{"q":"god","kind":"item", "item_type":"vocab","mode":"exact","limit":4}' | jq -r
```

Response body:
```json
{
  "hits": [
    {
      "ulid": "01KWDVQ6GMWPNTMY4CBSNSCDBE",
      "kind": "item",
      "lang": "en",
      "item_type": "vocab",
      "file_path": "items/vocab/god--01KWDVQ6GMWPNTMY4CBSNSCDBE.md",
      "title": "\"god\" 释义",
      "score": -2.062711172695435,
      "source": "fts",
      "chunk": null,
      "snippet": "# god\n\n## 给我的解释\n\n`god` 是英语名词，意为\"神、神灵\"，首字母大写 **God** 通常指一神论中的独一真神，小写 **god** 指多神教中的某一位神祇或比喻义。\n\n## 遇到记录\n\n- 2026-07-01：用户在学习英语时查询单词 god 并明确要求记住该单词的知识点。"
    }
  ],
  "count": 1,
  "took_ms": 0.15038899800856598
}
```

字段说明：
hits: 搜索结果

    kind: 匹配过滤条件：memory vault 文档分类。取值包括： 
        item : 知识类文档
        event ： 事件类文档
    item_type:  匹配过滤条件：知识类型 。取值包括： 
        kind=item 时，取值包括： vocab/phrase/grammar/pragmatics/others
        kind=event 为 NULL
    lang: 命中结果所属的目标学习语言。由 indexer 按请求 path 中的 lang 回填（不来自 documents 列）。
    file_path： 文件路径，相对该语言 vault 根（`$workspace/memory/languages/$lang/vault/`）的路径，不含 `{lang}/` 前缀。 可以使用 `mem_read_file` `mem_write_file` 等 mem 工具读写（mem 工具内部会按 lang 解析到对应 vault）。
    snippet: 匹配到的块文本

count： 搜索结果数


##### 示例 2 - 语义搜索 god

```bash
curl --unix-socket $workspace/indexer.sock http://localhost/en/search \
  -H 'Content-Type: application/json' \
  -d '{"q":"上帝","kind":"item","mode":"semantic","limit":4}' | jq -r
```

Response body:
```json
{
  "hits": [
    {
      "ulid": "01KWDVQ6GMWPNTMY4CBSNSCDBE",
      "kind": "item",
      "lang": "en",
      "item_type": "vocab",
      "file_path": "items/vocab/god--01KWDVQ6GMWPNTMY4CBSNSCDBE.md",
      "title": "\"god\" 释义",
      "score": 0.8090759962797165,
      "source": "vec",
      "chunk": {
        "chunk_id": 10,
        "section_title": "title",
        "section_kind": "frontmatter",
        "char_offset": 0,
        "text": "title: \"god\" 释义"
      },
      "snippet": "title: \"god\" 释义"
    },

    {
      "ulid": "01KWDVQ6GMWPNTMY4CBSNSCDBE",
      "kind": "item",
      "lang": "en",
      "item_type": "vocab",
      "file_path": "items/vocab/god--01KWDVQ6GMWPNTMY4CBSNSCDBE.md",
      "title": "\"god\" 释义",
      "score": 0.7707621157169342,
      "source": "vec",
      "chunk": {
        "chunk_id": 14,
        "section_title": "给我的解释",
        "section_kind": "explanation",
        "char_offset": 16,
        "text": "\n`god` 是英语名词，意为\"神、神灵\"，首字母大写 **God** 通常指一神论中的独一真神，小写 **god** 指多神教中的某一位神祇或比喻义。\n\n"
      },
      "snippet": "\n`god` 是英语名词，意为\"神、神灵\"，首字母大写 **God** 通常指一神论中的独一真神，小写 **god** 指多神教中的某一位神祇或比喻义。\n\n"
    }

  ],
  "count": 1,
  "took_ms": 3762.657223000133
}
```

字段说明：
hits: 搜索结果（字段意义同 示例 1，以下补充其它字段）
    chunk: 搜索匹配到的块说明
        section_kind: 取值：
            frontmatter: markdown 文件的 frontmatter
            其它: markdown 文件主体
        char_offset: 匹配到的块在 markdown 文件主体(不包括 frontmatter)中的字符 offset 。  section_kind=frontmatter 时总为 0 。
        text: 匹配到的块文本
    snippet: 匹配到的块文本


##### 示例 3 - hybrid 混合搜索

hybrid 混合搜索。混合了 全文搜索 和 语义搜索 的结果。

```bash
curl --unix-socket $workspace/indexer.sock http://localhost/en/search \
  -H 'Content-Type: application/json' \
  -d '{"q":"god","kind":"item","mode":"hybrid","limit":4}' | jq -r
```

Response body:
```json
{
  "hits": [
    {
      "ulid": "01KWDVQ6GMWPNTMY4CBSNSCDBE",
      "kind": "item",
      "lang": "en",
      "item_type": "vocab",
      "file_path": "items/vocab/god--01KWDVQ6GMWPNTMY4CBSNSCDBE.md",
      "title": "\"god\" 释义",
      "score": 0.01639344262295082,
      "source": "hybrid",
      "chunk": null,
      "snippet": "# god\n\n## 给我的解释\n\n`god` 是英语名词，意为\"神、神灵\"，首字母大写 **God** 通常指一神论中的独一真神，小写 **god** 指多神教中的某一位神祇或比喻义。\n\n## 遇到记录\n\n- 2026-07-01：用户在学习英语时查询单词 god 并明确要求记住该单词的知识点。"
    },
    {
      "ulid": "01KWDVQ6GMWPNTMY4CBSNSCDBE",
      "kind": "item",
      "lang": "en",
      "item_type": "vocab",
      "file_path": "items/vocab/god--01KWDVQ6GMWPNTMY4CBSNSCDBE.md",
      "title": "\"god\" 释义",
      "score": 0.01639344262295082,
      "source": "hybrid",
      "chunk": {
        "chunk_id": 9,
        "section_title": "headword",
        "section_kind": "frontmatter",
        "char_offset": 0,
        "text": "headword: god"
      },
      "snippet": "headword: god"
    }
  ],
  "count": 2,
  "took_ms": 1056.846970001061
}
```

字段说明：
混合了 示例 1，示例 2 的字段。

### GET /status

#### curl 示例

```bash
# 状态（聚合所有 lang DB）
curl --unix-socket $workspace/indexer.sock http://localhost/status
```  

#### Response 示例

```json
{
  "running": true,
  "uptime_s": 3600,
  "langs": [
    {
      "lang": "en",
      "tokenizer_version": "jieba:0.42+fugashi:1.1+unidic:2024...",
      "docs": 128,
      "chunks": 412,
      "embedded_chunks": 412,
      "embedding_model_id": "openai/text-embedding-3-small:1536"
    },
    {
      "lang": "ja",
      "tokenizer_version": "jieba:0.42+fugashi:1.1+unidic:2024...",
      "docs": 64,
      "chunks": 201,
      "embedded_chunks": 180,
      "embedding_model_id": "openai/text-embedding-3-small:1536"
    }
  ]
}
```

### POST /{lang}/index
Writer 投递该 lang vault 的索引请求

#### curl 示例

```bash
# Writer 投递索引请求（ja lang vault）
curl --unix-socket $workspace/indexer.sock http://localhost/ja/index \
  -H 'Content-Type: application/json' \
  -d '{"path":"items/vocab/aimai--01JZABD123.md"}'
```

注：`path` 相对 `$workspace/memory/languages/$lang/vault/`，不含 `{lang}/` 前缀。

### POST /{lang}/rebuild
全量重建该 lang DB

#### curl 示例

```bash
# 全量重建 ja lang DB
curl --unix-socket $workspace/indexer.sock -X POST http://localhost/ja/rebuild
```  
