# EverLingo Vault Editor Markdown 图片插入设计

- 状态：Accepted（2026-08-16，Phase 1-3 已实现完成）
- 作者：engineering
- 相关文档：
  - [Vault Editor 实现规范](/docs/impl-spec/vault-editor.md)
  - [Vault MCP 规范](/docs/impl-spec/vault-mcp/vault-mcp-spec.md)
  - [Vault MCP 工具定义](/docs/impl-spec/vault-mcp/vault-mcp-spec-tools.yaml)
  - [Image Store 设计](/docs/impl-spec/vision/image-store-spec.md)
  - [图片学习能力 ADR](/ADR/20260812-image-chat.md)
- 实现后需回填的文档：
  - `docs/impl-spec/vault-editor.md`（新增「图片插入」节、删除「不在本 spec 范围」中图片行）
  - `docs/impl-spec/vision/image-store-spec.md`（新增「Vault 图片存储」小节）
  - `TASKS.md`（记录改动）+ Release Notes

---

## 1. 背景与动机

[vault-editor.md](/docs/impl-spec/vault-editor.md) 当前只编辑 markdown 文本，不支持在笔记中嵌入图片。本 ADR 为 Vault Editor 增加「插入图片」能力：用户在编辑 markdown 时把图片写入 vault 并在文档中以标准 markdown 图片语法引用。

设计需同时满足：

1. 图片字节落盘到 vault，与 markdown 文件同生命周期、可被 indexer 索引体系之外的常规文件系统管理。
2. 前端在 Web Desktop 与 Web Mobile 下都能方便地插入图片（按钮 + 文件选择；移动端支持直接拍照）。
3. 复用既有的 [Image Store 预处理能力](/docs/impl-spec/vision/image-store-spec.md)（EXIF 校正 / 超限缩放 / sha256 完整性），避免重复实现。
4. 用户之后可在 vault 内**自由移动 / 重命名**图片文件——markdown 里的链接必须随之解析，不能假设图片永远待在某个固定目录。

---

## 2. 核心设计决策

### 决策 1：markdown 内保存**相对路径**，预览时改写为绝对 API URL

markdown 中保存的图片引用为**相对当前 markdown 文件所在目录**的路径，例如：

```markdown
![cat](hello-kitty.assets/2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1d0f.png)
```

- **保存形态用相对路径**：最贴合 vault「按目录组织、文件互相引用」的约定；markdown 可移植、与 `lang` 解耦；同一图片被多个笔记引用时各自持有正确的相对路径。
- **WYSIWYG 预览用绝对 URL**：浏览器渲染 `<img>` 需要可解析的 URL。编辑器在把内容交给 Milkdown 前，将相对链接解析为绝对 URL；在 `markdownUpdated` 回调（保存前）再逆改写为相对路径。Source 模式不渲染图片，直接展示原始相对 markdown，无需改写。

绝对 URL 形态（见决策 3）统一为 `/api/vault/raw/{lang}/{vault_rel_path}`，与「如何寻址一个 vault 文件」完全一致。

> 该相对↔绝对改写只针对图片链接（`![]((url))`）；其它 markdown 文本不被触动。

### 决策 2：图片链接是「指向 vault 内任意图片文件的路径」，不假设 `.assets` 位置

`{mdname}.assets/{src_sha}.{ext}` 只是**前端新增图片时的默认上传路径**，不是系统假设。用户之后把图片移到 `events/2026/x.png` 或重命名为 `photo.png` 后，markdown 里的链接（若随之更新或本就指向新位置）仍按「相对当前 md 目录解析 → vault 相对路径 → 绝对 URL」的规则正确渲染。

因此：
- 预览 GET 端点**不**限定路径含 `.assets`，按 vault 内任意文件服务。
- 上传 PUT 端点也**不**强制 `items/` 或 `.assets/`，仅做 vault 内逃逸校验 + 文件名 sha 完整性校验；默认 `.assets` 路径由前端构造。

### 决策 3：统一 vault 文件取回端点 `GET /raw/{lang}/{vault_rel_path:path}`

取消早期方案里的 `/api/vault/{lang}/asset/{...}` 特例段，统一为：

```http
GET /api/vault/raw/{lang}/{vault_rel_path}
```

- 服务**任意 vault 文件**（按扩展名定 Content-Type：图片 png/jpeg/webp → `image/*` inline；文本类 md/txt/json/yaml/csv → `text/plain`；其它 → `application/octet-stream`）。
- 信任边界与现有 `read?path=` 一致：先 `resolve()` 再校验 `is_relative_to(vault_root)`，逃逸即 400；文件不存在 404。
- 注册在 `vault_editor_api.py` 末尾，静态 GET 路由 `tree`/`read`/`tags` 已先注册并优先匹配，`write`/`append`/`search` 等是 POST 不冲突；router 带 `prefix="/api/vault"`，与 `web_acceptor` 的 `/editor`、catch-all 完全隔离。

markdown 图片链接 = `/api/vault/raw/{lang}/items/vocab/hello-kitty.assets/2cf….png`，与「寻址一个 markdown 文件」同形态，只是取回后用途不同（字节 vs JSON）。

### 决策 4：上传端点 `PUT /raw/{lang}/{vault_rel_path:path}`（multipart）

```http
PUT /api/vault/raw/{lang}/{vault_rel_path}
Content-Type: multipart/form-data
```

- 字段 `file=<binary>`。
- 服务端校验：vault 内不逃逸；末段文件名 stem 即前端 scale 前计算的原始 `src_resource_sha256`，服务端**仅校验其为 64 位 hex 格式**（不符 400），**不再对收到的字节重算比对**——前端可能已把图片缩放，缩放后字节 sha ≠ 原始 sha；MIME 属 `image/jpeg|image/png|image/webp`（否则 415）。
- 复用 `save_vault_image` 写盘（见决策 5）。同 sha 重复上传幂等（文件已存在则跳过写盘）。
- 前端默认构造 `{md_dir}/{mdname}.assets/{src_sha}.{ext}` 作为 `vault_rel_path`（`md_dir` 为 md 文件所在目录，如 `items/vocab`），但服务端不强制该形状。

### 决策 5：复用并扩展 `image_store.py`

在 `src/everlingo/image/image_store.py` 新增 `save_vault_image(lang, vault_rel_path, data: bytes, mime_type) -> ImageAsset`（**无状态、按路径幂等**）：

- 复用既有 `ALLOWED_MIME` / `preprocess_image`（EXIF 方向校正 → strip 元数据 → 超 1920×1200 按比例 LANCZOS 缩放）。
- 校验 `vault_rel_path` 末段 stem 为 64 位 hex（信任其为前端 scale 前计算的原始 `src_resource_sha256`）；不对收到的字节重算比对。
- 写盘到 `lang_vault_dir(lang).resolve() / vault_rel_path`（父目录自动建）。
- `storage_key = "memory://languages/{lang}/vault/{vault_rel_path}"`（逻辑键，对齐用户给定示例）。
- 返回 `ImageAsset`（含 `src_resource_sha256`、`saved_resource_sha256`、`mime_type`、`size`、`width`、`height`、`storage_key`、`created_at`）。
- best-effort：处理后对 JPEG 写 EXIF `UserComment="src_resource_sha256=..."`、PNG 写 `tEXt` 同名键（仅写入自有元数据，不影响隐私 strip）。

与既有的 session 图片存储（`ImageStore.save`，`storage_key=session://...`）并列，不改动其逻辑；vault 图片按路径在文件系统上持久存在，无需内存注册表。

### 决策 7：索引采用 include 逻辑（只 `*.md`），文件树展示全部

- 索引层全程是 **include 逻辑**：`walk_vault` / `sync.py` / `cli.py` 均以 `memory_root.rglob("*.md")` 枚举；`watcher.py` 每个事件先 `str(src_path).endswith(".md")` 才调 `parse_file`。因此图片（`.png`/`.jpeg`/`.webp`）**无论放在 `.assets/` 还是 vault 内任意位置，都不会被索引**。
- **`indexer.py` 零改动**：不再往 `is_excluded_vault_file` 加 `.assets` 排除（该排除既错误又冗余——图片本就不是 `.md`，天然不进 FTS/vec，watcher 也不会解析）。用户可自由移动 / 重命名图片，索引层无感知、无影响。
- **文件树展示真实 vault 结构**：`tree` 端点不特判 `.assets`、不隐藏图片文件；编辑器文件树照常显示图片文件与 `.assets` 目录，与「图片可放任意位置」一致。

### 决策 8：前端交互（按钮 + 文件选择，移动端拍照）

- 编辑器 sub-header 新增「插入图片」按钮（`ImageIcon` + 文字，`md:` 前缀隐藏文字，移动端仅图标）。
- 文件 `<input type="file" accept="image/jpeg,image/png,image/webp">`（与后端 415 对齐），移动端加 `capture="environment"`（直接拍照）。
- 处理流程：读文件 → **scale 前**算 `src_sha256`（hex，`sha256Hex` 原生/纯 JS 回退）→ 必要时 canvas 缩放到 ≤1920×1200（`scaleImageIfNeeded`，失败回退原图、后端兜底）→ `uploadImage(lang, {md_dir}/{mdname}.assets/{src_sha}.{ext}, blob, mime)` → 成功后在当前编辑器（source/wysiwyg）光标处插入（alt 用 md 文件名）。
- 前置校验：`currentPath` 为空（未保存的新文件）时禁用按钮并提示「请先保存文件」——因为 assets 目录依赖 markdown 文件名。
- 上传中按钮 loading；失败提示。

---

## 3. 端点 / 数据契约

### 上传（PUT）

```http
PUT /api/vault/raw/{lang}/{vault_rel_path}
Content-Type: multipart/form-data
```

请求：`file=<binary>`（路径中的 `{vault_rel_path}` 末段文件名即 `src_resource_sha256.ext`）。

成功响应：

```json
{
  "image": {
    "src_resource_sha256": "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1d0f",
    "saved_resource_sha256": "3cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1d0f",
    "mime_type": "image/jpeg",
    "width": 1280,
    "height": 1920,
    "size": 183240,
    "storage_key": "memory://languages/$lang/vault/items/vocab/hello-kitty.assets/2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1d0f.png",
    "created_at": "2026-08-16T14:00:00Z"
  }
}
```

错误语义：

| 场景 | HTTP | detail |
| --- | --- | --- |
| vault 路径逃逸 | 400 | `path escape` |
| MIME 不允许 | 415 | `unsupported mime type` |
| 空文件 | 400 | `empty file` |
| 末段文件名非合法 sha256（64 位 hex，应为前端 scale 前原始字节 sha） | 400 | `sha256 mismatch` |
| 图片不可解析 | 400 | `invalid image data` |

### 取回（GET，通用）

```http
GET /api/vault/raw/{lang}/{vault_rel_path}
```

- 校验 vault 内不逃逸（否则 400）；文件不存在 404；扩展名按上表定 Content-Type，`FileResponse` + immutable 缓存。
- 服务任意 vault 文件（图片 inline、文本类 text/plain、其它 octet-stream）。

### markdown 链接形态

```markdown
![alt](hello-kitty.assets/2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1d0f.png)
```

- 保存：相对当前 md 目录。
- 预览：编辑器改写为 `/api/vault/raw/{lang}/items/vocab/hello-kitty.assets/2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1d0f.png`（绝对 URL，浏览器可解析）。

---

## 4. 修改方案（文件级）

| 文件 | 改动 |
| --- | --- |
| `src/everlingo/image/image_store.py` | 新增 `save_vault_image(lang, vault_rel_path, data, mime)`，复用 `ALLOWED_MIME`/`preprocess_image`；stem 仅校验 64 位 hex 并作为 `src_resource_sha256`（不重算比对）；`storage_key=memory://...`；best-effort 写 EXIF/PNG 元数据 |
| `src/everlingo/gateway/vault_editor_api.py` | 新增 `PUT /raw/{lang}/{vault_rel_path:path}`（multipart）、`GET /raw/{lang}/{vault_rel_path:path}`（通用取回） |
| `web/src/editor/services/vaultApi.ts` | 新增 `uploadImage(lang, vaultRelPath, file, mimeType)`、`assetUrl(lang, vaultRelPath)` |
| `web/src/editor/types/vault.ts` | 新增 `ImageAsset` 类型 |
| `web/src/editor/services/imageLinks.ts`（新增） | `toDisplay` / `toRelative` 图片链接相对↔绝对改写 + `buildUploadPath`/`extFromMime`/`mdNameFromPath` 等路径工具 |
| `web/src/editor/services/imageScale.ts`（新增） | `scaleImageIfNeeded(file, maxPixels)` 必要时 canvas 等比缩放（失败回退原图）+ `shouldScale` |
| `web/src/editor/components/MilkdownEditor.tsx` | WYSIWYG 用 `toDisplay` 渲染、`markdownUpdated` 先 `toRelative`；经 `insertImageRef` 暴露光标插入（image 节点 src 用绝对 URL） |
| `web/src/editor/components/SourceEditor.tsx` | 经 `insertImageRef` 在光标处插入相对 `![alt](rel)` 文本 |
| `web/src/editor/components/EditorApp.tsx` | 新增「插入图片」按钮 + 文件选择（移动端 `capture`）+ 上传/插入流程 + `currentPath` 空校验 |

> 本 ADR 编写阶段**不**改动上述源文件，仅记录方案。

---

## 5. 分阶段执行计划

### Phase 1 — 后端闭环（优先，可独立 curl 验证）

1. `image_store.py` 新增 `save_vault_image`（sha 校验 / 幂等 / 预处理 / `memory://` storage_key / EXIF 元数据）。
2. `vault_editor_api.py` 新增 `PUT /raw/{lang}/{vault_rel_path:path}` 与 `GET /raw/{lang}/{vault_rel_path:path}`。
3. 单测：`save_vault_image`、通用 GET（含 vault 内逃逸拒绝、扩展名 Content-Type）。
4. 验收：`curl` 上传图片 → 回 `image` 对象 → `curl` GET 取回字节 → 浏览器可渲染。

### Phase 2 — 前端（含后端契约微调）

**Step 0 后端契约微调**（因「前端缩放 + 原始 sha 命名」）：`save_vault_image` 的 stem 校验由「重算收到的字节比对」改为「仅校验 64 位 hex 并作为 `src_resource_sha256`」（ADR 决策 4/5 已同步）；补缩放字节上传用例。

1. `vaultApi.ts` 加 `uploadImage` / `assetUrl`；`types/vault.ts` 加 `ImageAsset`。
2. 新增 `imageLinks.ts` 的 `toDisplay` / `toRelative` + 路径工具（`buildUploadPath`/`extFromMime`/`mdNameFromPath`），并补前端单测（相对↔绝对往返）。
3. 新增 `imageScale.ts` 的 `scaleImageIfNeeded`（必要时 canvas 等比缩放，失败回退原图）。
4. `MilkdownEditor` / `SourceEditor` 经 `insertImageRef` 接入改写与光标插入。
5. `EditorApp` 加「插入图片」按钮 + 文件选择（移动端 `capture`）+ 上传/插入流程（sha 先于 scale 计算）+ `currentPath` 空校验 + i18n 文案。
6. 验收：浏览器插入图片 → WYSIWYG 预览正常 → 保存为相对路径 → 重开仍为相对 → 移动/重命名图片后链接仍解析。

### Phase 3 — 文档回填（实现完成后）✅

- ✅ 更新 `vault-editor.md`：新增「图片插入」节、删除「不在本 spec 范围」图片行。
- ✅ 更新 `vault-mcp-spec-tools.yaml`（已核对：共 18 个工具，图片上传/取回不经 MCP，无新增工具；补充说明注释）。
- ✅ `image-store-spec.md` 新增「Vault 图片存储」小节。
- ✅ `TASKS.md` 记录改动 + 按 release-notes 规范写 Release Notes。

---

## 6. 风险与已知限制

- **WYSIWYG 插入最易出错**：Milkdown image 节点 src 必须用绝对 URL 才能预览，但保存必须回到相对路径；改写逻辑集中在 `imageLinks.ts` 与 `MilkdownEditor`，需单测覆盖往返。
- **用户移动图片后未更新链接**：链接指向旧位置会 404，属预期（MVP 不做自动重定位）。
- **无 base64 开销**：前端 PUT 端点直接调 `save_vault_image` 写盘，不经 MCP / 不做 base64 编解码，上传大图无额外开销。
- **stem 信任语义**：服务端不再对收到的字节重算 sha（前端缩放后字节 sha ≠ 原始 sha），仅格式校验并信任路径 stem；单用户本地场景可接受，内容寻址缓存语义不变（同一原始 sha → 确定性缩放 → 同一 URL/内容）。
- **前端缩放确定性**：canvas `toBlob` 跨浏览器可能产生不同 `saved_resource_sha256`，但文件按原始 sha 命名，去重/缓存不受影响。
- **多图 / 大图**：沿用 ADR §32 限制（单文件 ≤10MB、≤1920×1200、MIME 三选一）；MVP 不做多图并发优化。

---

## 7. 设计取舍记录

- **否决**早期 `/asset/` 特例段：与「如何寻址 vault 文件」脱节、无额外安全收益；改为统一 `GET /raw/{lang}/{vault_rel_path}`，信任边界与现有 `read` 一致。
- **否决** markdown 直接存绝对 API URL：破坏可移植性、与 `lang` 耦合；改为相对路径 + 编辑器改写。
- **否决** GET 限定 `.assets`：用户可自由移动图片；改为服务任意 vault 文件（扩展名定类型）。
- **否决** MCP `write_binary` 工具：当前无 agent 调用方（agent 只经 `write` 写 markdown，前端走 REST PUT），属无场景前置接口；YAGNI，从范围移除，MCP 端零改动、工具数维持 18。
- **否决** `.assets` 排除 / 特判：indexer 本就是 include 逻辑（只处理 `*.md`），图片无论放哪都不会被索引；改为依赖既有 include 逻辑，indexer 零改动，文件树也不特判图片。
