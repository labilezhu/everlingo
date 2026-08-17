# 把聊天图片沉淀到笔记（Chat → Vault Image）

- 状态：Accepted（2026-08-17）
- 作者：engineering
- 相关文档：
  - [图片学习能力后端 High-Level Design](/docs/ADR/20260812-image-chat.md)
  - [Vault Editor Markdown 图片插入设计](/docs/ADR/20260816-markdown-image.md)
  - [聊天图片需求文档](/docs/ADR/20260812-image-chat-requirement.md)
  - [Chat Agent 实现规范](/docs/impl-spec/chat-agent-spec.md)
  - [Memory Writer Agent 实现规范](/docs/impl-spec/memory-writer-agent-spec.md)
  - [Vault Editor 实现规范](/docs/impl-spec/vault-editor.md)
  - [Chat Agent 工具规范](/docs/impl-spec/chat-agent-tools-spec.md)
  - [Image Store 设计文档](/docs/impl-spec/vision/image-store-spec.md)

实现后需回填的文档：
- `docs/impl-spec/memory-writer-agent-spec.md`（新增「嵌入聊天图片」节）
- `docs/impl-spec/chat-agent-spec.md`（「笔记编辑」节补「嵌入聊天图片」子节）
- `docs/impl-spec/chat-agent-tools-spec.md`（新增 `copy_session_image_to_vault` 工具定义）
- `docs/impl-spec/vision/image-store-spec.md`（§3.1 更新 `save_vault_image` 签名）
- `TASKS.md`（记录改动）+ Release Notes

---

## 1. 背景与动机

完成以下 ADR 后，Chat Agent 已具备：
- 分析聊天上传图片的能力（[20260812-image-chat.md](/docs/ADR/20260812-image-chat.md)：Vision Service + `analyze_image` 工具，结果以 `ToolMessage` 落到对话历史）
- Vault 中 markdown 内嵌图片的能力（[20260816-markdown-image.md](/docs/ADR/20260816-markdown-image.md)：`save_vault_image` + 相对路径 + `GET/PUT /raw/...`）

但「把聊天中的图片写入笔记」这个闭环尚未打通。本 ADR 在既有基础设施之上，补充：
- 让新笔记（Memory Writer 异步 create 流程）与编辑笔记（Chat Agent 同步 edit 流程）都能把 session 图片复制到 vault，并在 markdown 中以相对路径引用。

典型场景：用户发一张错题图片 → Agent 分析讲解 → 用户「帮我记下来」→ 笔记里既含讲解正文，也含那张错题图片。

---

## 2. 现状关键事实（设计依据）

1. **图片字节来源**：聊天图片上传后经 `ImageStore.save()`（`web_acceptor.py:upload_image`）落盘到
   `{workspace}/sessions/{session_id}/images/{saved_sha}.{ext}`，并注册进进程内内存注册表 `ImageStore._registry`。
   取回用 `ImageStore.read_bytes(src_resource_sha256)`（见 `image_store.py:read_bytes`），返回**已预处理**字节。
2. **分析结论已在消息历史**：`analyze_image(src_resource_sha256)` 工具返回 `ImageAnalysis`（`src_resource_sha256` / `content_type` / `text` / `knowledge_points` …），以 `ToolMessage` 出现在 `new_messages` 与 Chat Agent 历史中。Writer Agent 的 `new_messages` 文本渲染（`_render_context_messages`）保留 `ToolMessage`，故 Writer LLM 能看到 `ImageAnalysis` 全文。
3. **`save_vault_image` 现状**：`save_vault_image(lang, vault_rel_path, data, mime_type)`，强制 `vault_rel_path` 末段 stem 为 64-hex `src_resource_sha256`（信任语义，不重算比对），写盘到 `lang_vault_dir(lang)/vault_rel_path`，幂等（已存在则跳过）；best-effort 把 `src_resource_sha256` 写入 JPEG EXIF / PNG tEXt 自有元数据。
4. **markdown 图片引用约定**（`vault-editor.md` 决策 1/2）：
   - 图片默认放在 `{md_dir}/{mdname}.assets/{name}.{ext}`；vault 根目录 md 则为 `{mdname}.assets/{name}.{ext}`。
   - markdown 内**只存相对当前 md 目录的路径**，预览时由编辑器改写为绝对 `/api/vault/raw/...` URL。
5. **两流程的工具注入点不同**：
   - 新笔记：Memory Writer Agent 内部 `asyncio.run(self._write_kb_item_async(entry))` 构建 per-entry LLM agent，工具来自 MCP `WANTED_TOOLS` 子集 + `vault_mcp_gen_id`（`mem_writer_agent.py:_write_kb_item_async`）。
   - 编辑：Chat Agent 同步调 `memory_writer_action`，`body` 由 Chat Agent LLM 构造（`agent.py:_refresh_agent_if_needed` 注入工具）。

---

## 3. 核心设计决策

### 决策 1：vault 图片文件名 = `{slug}-{src_sha前8位}.{ext}`

沿用「可读 + 唯一 + 幂等」三原则：

```text
{slug}-{src_sha[:8]}.{ext}
例：english-exercise-2cf24dba.png
```

- **slug**：来自 `ImageAnalysis` 的语义提示（如 `text` 片段或 `knowledge_points[0]`），经代码 slugify（小写、非 `[a-z0-9]+` 转 `-`、折叠连续 `-`、去首尾 `-`、限长 ~40 字符、空串回退 `"image"`）。
- **`-src_sha[:8]`**：保证唯一性与幂等（同一原图重复写入 → 同一路径 → `save_vault_image` 跳过写盘），且与现有「按路径幂等」语义自洽。
- 完整 `src_resource_sha256` 仍由 `_embed_self_metadata` 写入 EXIF/tEXt 自有元数据，溯源不丢。
- **否决**纯 `slug.ext`（同 slug 不同图会静默覆盖）、`slug.ext` + 数字去重（链路复杂、幂等弱）。

### 决策 2：`save_vault_image` 新增可选 kwarg `src_resource_sha256`

```python
def save_vault_image(
    lang: str,
    vault_rel_path: str,
    data: bytes,
    mime_type: str,
    *,
    src_resource_sha256: str | None = None,
) -> ImageAsset:
```

- `src_resource_sha256=None`（默认）→ **保留旧行为**：从 `vault_rel_path` stem 提取并校验 64-hex，作为 `src_resource_sha256`（前端 `vault_editor_api.py:upload_image` PUT 端点**零改动**）。
- 显式传入 → 跳过 stem 64-hex 校验，stem 可为任意 slug；`_embed_self_metadata` 用传入值。其余（MIME 校验、vault 逃逸校验、preprocess_image、幂等写盘）不变。

### 决策 3：新增 LLM 工具 `copy_session_image_to_vault`

图片复制由 LLM 工具触发（而非代码后处理），两流程共用同一工具，仅注入点不同。

```python
def make_copy_session_image_tool(image_store: ImageStore, target_lang: str) -> StructuredTool:
    @tool("copy_session_image_to_vault")
    async def copy_session_image_to_vault(
        src_resource_sha256: str,   # 来自 envelope.attachments / ImageAnalysis
        md_file_path: str,           # 本流程已决定的目标 md 相对路径
        slug_hint: str,              # LLM 从 ImageAnalysis 提炼的 1-3 个英文关键词
    ) -> str:                        # JSON: {"markdown_relative_path","vault_rel_path","mime_type"}
        ...
```

工具内部：
1. `data = image_store.read_bytes(src_resource_sha256)`；`None` → 返回错误 JSON（不抛异常，让 LLM 降级跳过该图）。
2. `asset = image_store.get(src_resource_sha256)` 取 `mime_type`（注册表必有，否则步骤 1 也不会有数据）。
3. `slug = slugify(slug_hint)`；`stem = f"{slug}-{src_resource_sha256[:8]}"`；`ext = _MIME_EXT[mime_type]`。
4. 路径构造（与 `vault-editor.md` 一致）：
   - `md_dir = posixpath.dirname(md_file_path)`
   - `mdname = posixpath.basename(md_file_path)[:-3]`（去 `.md`）
   - `assets_dir = f"{mdname}.assets"`
   - `vault_rel_path = f"{md_dir}/{assets_dir}/{stem}.{ext}"`（md_dir 为空时 `f"{assets_dir}/{stem}.{ext}"`）
5. `save_vault_image(target_lang, vault_rel_path, data, mime_type, src_resource_sha256=src_resource_sha256)`。
6. `markdown_relative_path` = 相对于 `md_dir`（即 `f"{assets_dir}/{stem}.{ext}"`，md_dir 为空时同形）。
7. 返回 `{"markdown_relative_path": ..., "vault_rel_path": ..., "mime_type": ...}` 的 JSON 字符串。

**关键设计**：工具返回 `markdown_relative_path`，LLM 直接把该值填进 `![<alt>](<markdown_relative_path>)`，**不做路径算术**，避免链接写错（契合 `vault-editor.md` 决策 1「markdown 只存相对路径」）。

### 决策 4：两流程注入同一工具，步骤顺序由 prompt 约束

| 流程 | 谁调用复制工具 | 工具注入位置 |
|---|---|---|
| 新笔记（create） | Memory Writer LLM | `mem_writer_agent.py:_write_kb_item_async`：MCP `tools` 加载后 `tools = list(tools) + [make_copy_session_image_tool(image_store, entry.lang)]` |
| 编辑（edit） | Chat Agent LLM | `agent.py:_refresh_agent_if_needed`：仅当 `channel_metadata.supported_image` 时，`self._tools.append(make_copy_session_image_tool(image_store, self._target_lang))` |

`image_store` 取自 `everlingo.image.image_store.image_store` 进程级单例（两 Agent 同处 gateway 进程）。

**执行顺序约束**（注入 prompt 子节，见 §4）：必须先复制图片拿到 `markdown_relative_path`，再写含图片引用的 markdown 正文。

### 决策 5：MemoryEntry 结构无需改动

- 编辑流程的 `body` 已能承载含图片 markdown 引用的正文，无需新字段。
- 创建流程由 Writer LLM 在 `body` 内自行嵌入图片引用，无需新字段。
- `mem_entry_spec.md` 字段范围保持现状。

---

## 4. 待回填到各 spec 文件的内容

> 以下片段在对应 spec 「实现完成后」回填；本 ADR 先记录目标内容，避免实现走样。

### 4.1 `docs/impl-spec/vision/image-store-spec.md` §3.1 更新

在「Vault 图片存储」节追加：

```text
save_vault_image 签名（2026-08-17 扩展）：
  save_vault_image(lang, vault_rel_path, data, mime_type, *, src_resource_sha256=None)
  - src_resource_sha256=None（默认）：保留旧行为，从 vault_rel_path 末段 stem 提取并校验
    64 位 hex（前端 PUT 上传契约不变）。
  - 显式传入 src_resource_sha256：跳过 stem 64-hex 校验（stem 可为英文 slug），EXIF/PNG 元数据
    用传入值写入。供 Chat Agent / Memory Writer 从 session 图片复制入 vault 时使用。
  ref: docs/ADR/20260817-save-image-from-chat-to-note.md — 决策 2
```

### 4.2 `docs/impl-spec/chat-agent-tools-spec.md` 新增工具节

```text
## 聊天图片复制到 Vault - copy_session_image_to_vault

toolset name: copy_session_image_to_vault
toolset description: 把当前会话上传的图片复制到笔记 vault，返回 markdown 相对引用路径。

### functions

#### copy_session_image_to_vault
function name: copy_session_image_to_vault
function description: 把聊天 session 中某张已上传图片复制到目标笔记 markdown 的 .assets 目录，
  返回可在 markdown 正文中直接使用的相对引用路径。仅当 channel 支持图片时注入 Chat Agent。
parameters:
    src_resource_sha256: string。图片在 envelope.chat.attachments / analyze_image 结果中的标识。
    md_file_path: string。目标笔记 markdown 的 vault 相对路径（如 items/vocab/aimai--01JZABD123.md）。
    slug_hint: string。从 ImageAnalysis 提炼的 1-3 个英文关键词，用于生成可读文件名。
returns: string。JSON：{"markdown_relative_path": "...", "vault_rel_path": "...", "mime_type": "..."}。
  失败（如图片字节不可取）返回 {"ok": false, "error": "..."}。
```

### 4.3 `docs/impl-spec/memory-writer-agent-spec.md` 新增「嵌入聊天图片」节

```text
## 嵌入聊天图片（create 流程）

ref: docs/ADR/20260817-save-image-from-chat-to-note.md

Memory Writer 处理带图片 attachment 的会话时，可在新建/合并的笔记中嵌入该图片：

1. 经 vault_mcp_gen_id 确定目标 md_file_path（沿用既有 vault_spec 命名）。
2. 对每张要嵌入的 session 图片，调用 copy_session_image_to_vault(src_resource_sha256,
   md_file_path, slug_hint)；slug_hint 取自 new_messages 中 ImageAnalysis 的 text / knowledge_points。
3. 工具返回 markdown_relative_path；在 markdown 正文用 ![alt](markdown_relative_path) 嵌入。
4. 之后才经 vault_mcp_write 写入 md 文件。
5. 输出写入确认 JSON（updated_files / update_summary / conversation_context）。

约束：
- 必须先复制图片再写 md，避免 body 中链接与实际文件路径不一致。
- 工具取不到图片字节（返回 ok=false）时，正文跳过该图，不中断写入。
- image_store 为进程内注册表，进程重启后无法取回；此限制与 session 上下文同生命周期，可接受。
```

### 4.4 `docs/impl-spec/chat-agent-spec.md` 「笔记编辑」节补「嵌入聊天图片」子节

```text
#### 嵌入聊天图片（编辑流程）

编辑笔记需嵌入本轮聊天中的图片时：
1. 按既有定位/确认流程获得 md_file_path（必须已 vault_mcp_read 加载最新原文件）。
2. 对每张要嵌入的 session 图片，先调用 copy_session_image_to_vault(src_resource_sha256,
   md_file_path, slug_hint)（slug_hint 来自本轮 analyze_image 结果的 text / knowledge_points），
   拿到 markdown_relative_path。
3. 在 memory_writer_action(operation="edit", body=...) 的 body 中用 ![alt](markdown_relative_path) 嵌入。
4. 必须先复制图片再调 memory_writer_action（复制工具产出 body 所需的相对路径）。

仅当 channel 支持图片时该工具可用（与 analyze_image 同注入条件）。
```

---

## 5. 修改方案（文件级）

| 文件 | 改动 |
| --- | --- |
| `src/everlingo/image/image_store.py` | `save_vault_image` 新增可选 kwarg `src_resource_sha256`（默认 None 保留旧行为）；新增模块级 `slugify(text)->str` 工具供复制工具复用 |
| `src/everlingo/tools/image_vault_copy.py`（新增） | `make_copy_session_image_tool(image_store, target_lang)` + `copy_session_image_to_vault` 工具（见决策 3） |
| `src/everlingo/agents/agent.py` | `_refresh_agent_if_needed`：当 `channel_metadata.supported_image` 时注入 `copy_session_image_to_vault`；「笔记编辑」system prompt 节补「嵌入聊天图片」子节 |
| `src/everlingo/mem/agents/mem_writer_agent.py` | `_write_kb_item_async`：MCP tools 加载后追加 `copy_session_image_to_vault`；Writer system prompt 新增「嵌入聊天图片」节 |
| `docs/impl-spec/vision/image-store-spec.md` | §3.1 补 `src_resource_sha256` 可选 kwarg 说明 |
| `docs/impl-spec/chat-agent-tools-spec.md` | 新增 `copy_session_image_to_vault` 工具节 |
| `docs/impl-spec/memory-writer-agent-spec.md` | 新增「嵌入聊天图片」节 |
| `docs/impl-spec/chat-agent-spec.md` | 「笔记编辑」节补「嵌入聊天图片」子节 |
| `tests/test_image_store.py` | 补 `save_vault_image` 显式 `src_resource_sha256` 用例（slug stem + 显式 sha） |
| `tests/test_image_vault_copy.py`（新增） | `slugify` 边界 + `copy_session_image_to_vault` 成功/失败/幂等/根目录路径 用例 |
| `tests/test_mem_writer_agent.py` | 补 Writer tools 含 `copy_session_image_to_vault` 注入断言（mock image_store） |
| `TASKS.md` + Release Notes | 记录改动 |

---

## 6. 测试要点

- `save_vault_image` 显式 `src_resource_sha256`：slug stem + 显式 sha → 正确落盘 + EXIF/tEXt 含 src_sha；旧行为（None）回归保持。
- `slugify`：空串 → `"image"`；含空格/大写/非 ASCII → 小写 `-` 分隔且限长；连续分隔符折叠。
- `copy_session_image_to_vault`：
  - 成功：返回 `markdown_relative_path` 正确、文件落盘到 `{mdname}.assets/`、EXIF 含 src_sha。
  - `image_store.read_bytes` 返回 None（模拟进程重启）→ 工具返回 `{"ok":false}` 且不抛。
  - 幂等：同 src_sha + 同 slug_hint 两次调用 → 同一路径、不重复写盘。
  - md 在 vault 根目录（`md_file_path` 无目录）vs 子目录的路径计算均正确。
- Writer 注入：mock `image_store` 断言 `_write_kb_item_async` 的 tools 含 `copy_session_image_to_vault`。

---

## 7. 风险与已知限制

- **进程内存注册表**：`ImageStore._registry` 为进程内态，`read_bytes` 仅能取回当前 gateway 进程生命周期内上传的图片。进程重启后注册表清空，复制工具返回失败（LLM 降级跳过）。因 `MainAgent._messages` 同为内存态，重启后 Agent 也无 `src_resource_sha256` 可用，限制一致、可接受。留作 P1。
- **二次预处理**：`read_bytes` 返回已预处理字节，再进 `save_vault_image` 会二次 `preprocess_image`（幂等无害，仅多一次 Pillow 开销）。MVP 不优化；如需可加 `_skip_preprocess` 内部分支。
- **MD 根目录 `.assets`**：vault 根目录 md 的图片落 `{mdname}.assets/` 于 vault 根（与 `vault-editor.md` 约定一致），非会话目录。
- **不做内容级去重**：不同 slug 指向同一图时按路径独立存储（与现有编辑器行为一致），靠 `(slug, sha8)` 路径幂等避免同图重复写盘。

---

## 8. 设计取舍记录

- **否决**纯 slug 文件名：碰撞覆盖风险。
- **否决** `save_vault_image` 彻底改为必传 `src_resource_sha256`（破坏前端 PUT 契约、需同步改 `vault-editor.md`）：改为可选 kwarg，向后兼容。
- **否决**代码后处理（LLM 输出 image_copies 计划再批量复制）：时序复杂、body 链接易错位；改用 LLM 工具即时复制并回传相对路径。
- **否决** LLM 直出最终文件名：非 ASCII/超长/幻觉风险；改为 LLM 给 hint + 代码 slugify 归一化。
