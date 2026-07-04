# Search API spec

## REST 端点

| 方法 路径 | 用途 | 请求 body | 响应 |
|---|---|---|---|
| `POST /search` | 全文检索 | `{q, lang?, item_type?, tags?, kind?, mode, limit}` | `{hits:[...], count, took_ms}` |
| `POST /index` | Writer 投递索引请求 | `{path}` | `{ok}` |
| `POST /delete` | 删除指定文件索引 | `{path}` | `{ok}` |
| `POST /rebuild` | 全量重建 | `{}` | `{ok, indexed, chunks, took_ms}` |
| `GET /status` | 查询状态 | — | `{running, tokenizer_version, docs, chunks, uptime_s}` |

### POST /search
搜索 vault

#### Request body
Request: {q, lang?, item_type?, tags?, kind?, mode, limit}

字段说明：

q: 要匹配的文本
lang:       匹配过滤条件：目标学习语言。如 en,ja,zh-CN
kind:       匹配过滤条件：memory vault 文档分类。取值包括： 
    item : 知识类文档
    event ： 事件类文档
    user ： 用户偏好类文档
item_type:  匹配过滤条件：知识类型 。取值包括： 
    kind=item 时，取值包括： vocab/phrase/grammar/pragmatics/others
    kind=event/user 为 NULL
mode: 搜索模式。取值包括： 
    exact ： 全文精确搜索
    semantic ： 语义搜索
    hybrid ： 混合搜索。混合以上两人种搜索的结果
limit: 搜索返回结果数限制


#### curl 示例

```bash
# 搜索含 "god" mode: hybrid
curl --unix-socket $workspace/index/indexer.sock http://localhost/search \
  -H 'Content-Type: application/json' \
  -d '{"q":"god","mode":"hybrid","limit":4}' | jq -r 
```

#### Response body

##### 示例 1 - 全文搜索含 "god" 的词语
```bash
curl --unix-socket $workspace/index/indexer.sock http://localhost/search \
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
      "lang": null,
      "item_type": "vocab",
      "file_path": "en/items/vocab/god--01KWDVQ6GMWPNTMY4CBSNSCDBE.md",
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
        user ： 用户偏好类文档
    item_type:  匹配过滤条件：知识类型 。取值包括： 
        kind=item 时，取值包括： vocab/phrase/grammar/pragmatics/others
        kind=event/user 为 NULL
    file_path： 文件路径，Memory Vault 相对路径。 可以使用 `mem_read_file` `mem_write_file` 等 mem 工具读写。
    snippet: 匹配到的块文本

count： 搜索结果数


##### 示例 2 - 语义搜索 god

```bash
curl --unix-socket $workspace/index/indexer.sock http://localhost/search \
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
      "lang": null,
      "item_type": "vocab",
      "file_path": "en/items/vocab/god--01KWDVQ6GMWPNTMY4CBSNSCDBE.md",
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
      "lang": null,
      "item_type": "vocab",
      "file_path": "en/items/vocab/god--01KWDVQ6GMWPNTMY4CBSNSCDBE.md",
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

```bash
curl --unix-socket $workspace/index/indexer.sock http://localhost/search \
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
      "lang": null,
      "item_type": "vocab",
      "file_path": "en/items/vocab/god--01KWDVQ6GMWPNTMY4CBSNSCDBE.md",
      "title": "\"god\" 释义",
      "score": 0.01639344262295082,
      "source": "hybrid",
      "chunk": null,
      "snippet": "# god\n\n## 给我的解释\n\n`god` 是英语名词，意为\"神、神灵\"，首字母大写 **God** 通常指一神论中的独一真神，小写 **god** 指多神教中的某一位神祇或比喻义。\n\n## 遇到记录\n\n- 2026-07-01：用户在学习英语时查询单词 god 并明确要求记住该单词的知识点。"
    },
    {
      "ulid": "01KWDVQ6GMWPNTMY4CBSNSCDBE",
      "kind": "item",
      "lang": null,
      "item_type": "vocab",
      "file_path": "en/items/vocab/god--01KWDVQ6GMWPNTMY4CBSNSCDBE.md",
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
# 状态
curl --unix-socket $workspace/index/indexer.sock http://localhost/status
```  

### POST /index
Writer 投递索引请求

#### curl 示例

```bash
# Writer 投递索引请求
curl --unix-socket $workspace/index/indexer.sock http://localhost/index \
  -H 'Content-Type: application/json' \
  -d '{"path":"ja/items/vocab/aimai--01JZABD123.md"}'
```  

### POST /rebuild
全量重建

#### curl 示例

```bash
# 全量重建
curl --unix-socket $workspace/index/indexer.sock -X POST http://localhost/rebuild
```  