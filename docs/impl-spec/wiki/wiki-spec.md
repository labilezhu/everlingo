# Wiki

把 [Memory Vault](/src/everlingo/mem/vault/vault_specs/default/vault_spec.md) 中的 markdown 渲染成可浏览、可搜索的静态网站，让用户方便地回顾自己的语言学习知识库。

## 范围

- **Phase 1**：单用户、本地运行。多目标学习语言（target language）支持。
- **Phase 2 及以后**：多用户、远程部署、接入现有语义搜索 API（见「未来演进」）。

## 选型决策

静态站点生成器选用 **[Quartz 5](https://quartz.jzhao.xyz/)**。

理由：

1. **与 vault frontmatter 原生兼容**。vault spec 已规定 `title` / `description` / `tags` / `aliases` / `related` / `slug` 字段，Quartz 原生读取这些字段并生成 backlinks、graph view、tag 索引、alias 重定向页——几乎零改造。
2. **内置知识库特性**：backlinks、graph view、full-text search、folder listing、breadcrumbs、popover preview。这些是 MkDocs / VitePress 需要大量插件或自研才能补齐的。
3. **相对 URL 策略**：Quartz 5 优先使用相对 URL（见「Spike 验证」），天然支持子路径部署，适合多语言 vault 的按语言挂载方案。

不选 MkDocs / VitePress 的原因：两者面向产品文档而非个人知识库，缺少 backlinks/graph/aliases 这类 vault 语义，强行补齐成本高于直接用 Quartz。

## 架构

Wiki 是**独立进程**，不与 [Web Session Acceptor](/docs/impl-spec/web-session-acceptor.md) 复用 web server。

理由：

1. **关注点不同**。web_acceptor 服务于「对话流」（Session/Channel/Agent 生命周期、SSE 推送、超时回收）；wiki 服务于「静态内容浏览 + 搜索」。强行复用会让 web_acceptor 同时承担两套不相关职责，且 Session 超时回收逻辑会误伤 wiki 长连接。
2. **构建/部署独立**。wiki 本质是 static site，vault 变化时 rebuild，不应影响正在进行的 chat session。
3. **可演进**。本地单用户阶段 = 静态文件 + 简单 static server；未来多用户/上云阶段可独立部署到静态托管，不耦合 gateway。

进程模型与 gateway 平级，**不**通过 `gateway --channel_*` 参数混入。入口形态见 [app-entry.md](/docs/impl-spec/app-entry.md)（需补充 `everlingo wiki` 子命令说明）。

```
~/.everlingo/workspaces/<ws>/
  memory/languages/<lang>/vault/    ← 输入：每语言独立 vault
  .wiki-dist/                       ← 输出：构建产物（见「构建产物布局」）

<repo>/tools/wiki/quartz/           ← Quartz 工程（git submodule，见「Quartz 源码管理」）
```

## 工程结构

```
src/everlingo/wiki/
  __init__.py
  cli.py        # `everlingo wiki build|serve` 子命令分发
  builder.py    # 枚举 lang vault、组装 content、调用 Quartz build、生成首页
  server.py     # uvicorn + StaticFiles 服务构建产物

tools/wiki/quartz/                  # git submodule，pin Quartz 上游版本
  quartz.config.yaml                # 我们的定制配置（见「Quartz 配置定制」）
  content/                          # 构建时 symlink 到当前 lang vault（临时）

tests/
  test_wiki_cli.py
  test_wiki_builder.py
  test_wiki_server.py
```

## 构建流程 `everlingo wiki build`

对当前 workspace 下每个目标语言 vault 各跑一次 Quartz build，最后生成站点根首页。

```
1. langs = workspace.lang_dirs()           # 枚举 $ws/memory/languages/*/（见 workspace.py:175）
2. for lang in langs:
     a. 在 <quartz_dir>/content 建临时 symlink → $ws/memory/languages/<lang>/vault
     b. 注入临时 index.md 到 vault 根（见「Vault 根 index.md」）
     c. 执行 `npx quartz build --directory <quartz_dir> --output <dist_dir>/<lang>`
     d. 清理 symlink 与临时 index.md
3. 生成 <dist_dir>/index.html（见「首页与语言选择」）
```

### 构建产物布局

```
<dist_dir>/                          # 默认 $workspace/.wiki-dist/
  index.html                         # 我们生成：语言选择页 / 单语言重定向
  en/                                ← Quartz 完整站点产物
    index.html
    items/...
    events/...
    spec/...
    tags/...
    static/...                       # contentIndex.json（搜索索引）等
    *.css *.js                       # 框架资源（相对路径引用）
  ja/
    ...
```

每语言是**独立的完整 Quartz 站点**，自带 CSS/JS/搜索索引，互相完全隔离。

### Vault 根 index.md

Quartz **不自动生成站点根 `index.html`**——若 vault 根没有 `index.md`，该语言站点首页 `/en/` 会 404（spike 验证）。

builder 在每次 build 前**临时**向 vault 根注入一个 `index.md`，build 完成后**立即删除**，不污染用户 vault。内容模板示例：

```markdown
---
title: <语言名> 知识库
description: <语言名> 学习笔记、词汇与语法
---
# <语言名> 知识库
```

（语言名从 `user_profile.language` 或 lang 代码映射得到。具体模板字段在实现时确定。）

## 服务流程 `everlingo wiki serve`

启动一个 uvicorn 进程，用 `StaticFiles` 挂载构建产物：

```python
# 伪代码
app = Starlette()
app.mount("/", StaticFiles(directory=dist_dir, html=True))
uvicorn.run(app, host="127.0.0.1", port=wiki_port)
```

`StaticFiles(html=True)` 关键能力：
- 目录请求自动返回 `index.html`（`/en/` → `en/index.html`）
- 无扩展名请求自动追加 `.html`（`/en/items/vocab/ambiguous--01jzabc456` → `.../.html`）
- `/en/tags/vocab` → `en/tags/vocab.html`

不监听 vault 变化（Phase 1 手动 build）。serve 进程不依赖 gateway、indexer 等其它进程。

## 首页与语言选择

站点根 `<dist_dir>/index.html` 由 builder 生成（Quartz 不生成它）：

- **单语言**：HTTP meta refresh 或 JS `location.replace` 自动跳转到 `/<lang>/`。
- **多语言**：静态语言选择页，列出所有 lang，每个卡片链接到 `/<lang>/`。

首页是纯静态 HTML，不依赖 Quartz 资源。

## 配置项

扩展 [configuration.md](/docs/impl-spec/configuration.md)（实现时同步更新），新增：

| 字段 | 默认值 | 说明 |
|---|---|---|
| `wiki_dist_dir` | `$workspace/.wiki-dist` | 构建产物输出目录 |
| `wiki_port` | `8765` | wiki serve 监听端口（避开 chatbot web 端口） |
| `wiki_quartz_dir` | `<repo>/tools/wiki/quartz` | Quartz 工程目录，允许用户指向自己的 fork 做主题定制 |

## Vault 内容处理

### 纳入 wiki 的子目录

| 目录 | 处理 | 说明 |
|---|---|---|
| `items/` | ✅ 进 | 知识点笔记（核心内容） |
| `events/` | ✅ 进 | 每日学习事件，时间线回溯 |
| `spec/` | ✅ 进 | 每语言 vault 各自的规范文件（用户已确认「各 lang 各自进」） |
| `tmp/` | ❌ 忽略 | vault spec 明确「不索引」；通过 Quartz `ignorePatterns` 排除 |

### Quartz `ignorePatterns` 配置

```yaml
ignorePatterns:
  - private
  - templates
  - .obsidian
  - tmp
  - tmp/**
```

### Frontmatter 兼容性（spike 验证）

vault frontmatter 字段到 Quartz 行为的映射：

| vault 字段 | Quartz 行为 |
|---|---|
| `title` | 页面标题、搜索索引 ✅ 原生 |
| `description` | 页面摘要、搜索索引 ✅ 原生 |
| `tags` | tag 索引页（`/en/tags/<tag>`）、属性面板展示 ✅ 原生 |
| `aliases` | 生成 alias 重定向页（`模棱两可.html` → 跳转到主页面）✅ 原生 |
| `slug` | 决定 URL path（文件名主体）✅ 原生 |
| `related` | Quartz 不识别，但会被 backlinks 语义覆盖（不丢失信息） |
| `type` | 已作为 tag 记入 `tags`（vault spec 规定），无需额外处理 |
| `description_in_target_lang` | 不进搜索索引；可在 Quartz 配置中加为展示字段（可选） |

## 搜索

Phase 1 使用 Quartz 内置的 [Full-text Search](https://quartz.jzhao.xyz/features/full-text-search)（客户端 FlexSearch 索引，产物在 `static/contentIndex.json`）。

- **天然按语言隔离**：每语言是独立 build，各自有独立的 `contentIndex.json`。`/en/` 站点搜不到 `ja` vault 内容——与 workspace.md 中「per-lang SQLite 隔离」的设计原则一致。
- 跨语言搜索是「未来演进」项，Phase 1 不支持。

## Quartz 源码管理

采用 **git submodule** 指向 `jackyzha0/quartz` 上游，pin 到稳定 tag。

```bash
git submodule add https://github.com/jackyzha0/quartz.git tools/wiki/quartz
cd tools/wiki/quartz && git checkout v5.x.x
```

我们的定制（config、layout、可能的插件）以 **overlay** 形式存在：

- `tools/wiki/quartz/quartz.config.yaml` — 我们的定制配置（覆盖默认）
- 首次 build 前 builder 检查 `.quartz/plugins/` 是否就绪，未就绪时调用 `npx quartz plugin install --from-config` 安装社区插件

上游升级时 rebase 我们的 overlay。如果未来需要深度改 layout/主题，可把 submodule 换成 fork（见「未来演进」）。

## Quartz 配置定制

`tools/wiki/quartz/quartz.config.yaml` 关键定制项（相对 Quartz 默认）：

```yaml
configuration:
  pageTitle: EverLingo Wiki
  enableSPA: true              # 保留 SPA routing（spike 验证子路径可用）
  enablePopovers: true
  analytics: null              # 关闭外部分析
  locale: zh-CN                # UI 语言（与界面语言一致；多语言 vault 共用同一界面语言）
  baseUrl: localhost           # 必须为有效值（spike 发现空字符串会导致 new URL() 抛错）
  ignorePatterns:
    - tmp
    - tmp/**
    # ... 其余默认
plugins:
  # 使用 Quartz 默认插件集（explorer / graph / search / backlinks / tag-page 等）
  # 关闭 comments、explicit-publish 等不需要的
  # ...
```

`baseUrl` 的取舍：它只影响 og:url / sitemap / RSS 中的绝对 URL（用于社交分享与 SEO），不影响页面内导航（导航全用相对 URL）。Phase 1 本地场景设为 `localhost` 即可。

## Spike 验证记录

2026-07-16 用临时测试 vault（en/ja 各含 items/events/spec/tmp，frontmatter 符合 vault spec）跑通完整流程，确认：

1. **Quartz 5 所有资源用相对 URL**：CSS/JS/图片/`contentIndex.json` 全是 `../../xxx`、`./xxx`，无硬编码 `/` 前缀。
2. **SPA routing 显式处理相对路径**：`script-11` 中的 `gu(D, u)` 用 `new URL(relativePath, fetchedPageUrl)` 把所有相对 `href`/`src` 转成绝对 pathname，自然带上 `/<lang>/` 前缀。
3. **不需要 `--baseDir` 标志**：Quartz 的相对 URL 策略 + 浏览器对相对 href 的自动解析，已足够支撑子路径部署。`--baseDir` 是 GitHub Pages 子路径场景用的，我们的 per-lang 独立 build 不需要它。
4. **多语言子路径布局可行**：`<dist>/{en,ja}/` 各为完整 Quartz 站点 + 根 `index.html`（语言选择页），`StaticFiles(html=True)` 可正确路由所有内部链接。
5. **vault 根需有 `index.md`**：否则每语言站点首页 404——builder 需注入临时 `index.md`。
6. **`baseUrl` 不能为空字符串**：`Head.tsx` 会 `new URL("https://")` 抛 `Invalid URL`。设为 `localhost` 即可。
7. **`tmp/` 通过 `ignorePatterns` 正确排除**：4 个真实文件被索引，tmp 下的文件未进 build。
8. **aliases 生成重定向页**：`aliases: [模棱两可]` → 生成 `模棱两可.html` 跳转到主 slug 页面 ✅。

## 测试策略

遵循 [TEST_STYLE.md](/TEST_STYLE.md)（实现时阅读）。

- `test_wiki_cli.py`：子命令分发、参数校验、`--workspace` 透传
- `test_wiki_builder.py`：mock subprocess 验证 Quartz 调用参数、contentDir 解析、`index.md` 注入/清理、错误处理（Node 缺失 / npm 失败 / vault 路径无效 / 无 lang 目录）
- `test_wiki_server.py`：StaticFiles 挂载、端口绑定、根首页返回（轻量，可用 TestClient）

Quartz 自身的渲染正确性不纳入我们的测试范围（上游负责）。

## 未来演进

- **跨语言搜索**：Phase 1 Quartz 内置搜索按 lang 隔离。若用户需要「同时看 en/ja 中关于 ambiguity 的笔记」，需把 wiki 搜索接到现有 `/{lang}/search` API（[search-api-spec.md](/docs/impl-spec/search/search-api-spec.md)），在 `quartz.config.yaml` 禁用内置 search 插件并自研前端搜索组件。代价：wiki serve 进程依赖 indexer 在线。
- **Graph view 活跃**：当前 vault 正文无 `[[wikilinks]]`，graph view 几乎是孤点。可选：build 时后处理把 `related`/`aliases` 渲染成正文 `[[...]]` 链接；或让 memory writer agent 今后主动用 `[[...]]` 链接（更深的产品决策）。
- **Quartz fork**：若定制深入到 layout/主题层，把 submodule 换成我们自己的 fork。
- **ROADMAP 归属**：Wiki 属 Phase 2 特性（Phase 1 DEMO 仍是 TUI）。实现时在 [ROADMAP.md](/ROADMAP.md) Phase 2 节正式登记。

## 参见

- [Vault Spec](/src/everlingo/mem/vault/vault_specs/default/vault_spec.md) — vault 目录结构与 frontmatter 规范
- [Workspace](/docs/impl-spec/worksplace/workspace.md) — 多语言 vault 布局（`memory/languages/<lang>/vault`）、`lang_dirs()`
- [App Entry](/docs/impl-spec/app-entry.md) — 进程入口约定（需补充 `everlingo wiki`）
- [Web Session Acceptor](/docs/impl-spec/web-session-acceptor.md) — 为什么不复用其 web server
- [Search API Spec](/docs/impl-spec/search/search-api-spec.md) — 未来跨语言搜索的接入点
- [Configuration](/docs/impl-spec/configuration.md) — 配置项扩展点
