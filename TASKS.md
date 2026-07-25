# Current Sprint

## 进行中的任务

## 完成的任务
格式：完成日期与时间(北京时间) | 任务描述 。 示例：" - 2026-06-20 19:28 | 生成主入口代码"
- 2026-07-25 22:48 | **GitHub Actions 多架构镜像发布 CI**
  - 新建 `.github/workflows/docker-release.yml`：`v*` tag / `workflow_dispatch` 触发；双 native runner（amd64=`ubuntu-24.04`，arm64=`ubuntu-24.04-arm`）并行 build，再 `manifest` job 用 `docker buildx imagetools create` 合并为多架构 manifest
  - Tag 规则：`v1.2.3`→`1.2.3`/`1.2`/`1`/`latest`；`v1.2.3-rc.1`→`1.2.3-rc.1`/`1.2.3`（无 latest）；dispatch→`dev-<run_id>` 或 `dev-<run_id>-<suffix>`
  - metadata-action 生成 base tag，自定义 step 用 sed 给每条 tag 追加 `-amd64`/`-arm64` 后缀作为单架构镜像 tag；manifest job 遍历 base tag 列表合并
  - GHA cache `type=gha,mode=max`，scope 分 arch（`everlingo-amd64`/`everlingo-arm64`）
  - GHCR 认证用默认 `GITHUB_TOKEN`；permissions `contents: read`/`packages: write`
  - 新建 `docs/impl-spec/CI/github-ci-spec.md`：触发条件、构建策略、tag 规则、GHCR 可见性配置、仓库权限要求、发布流程、链接到 container-spec.md

- 2026-07-25 XX:XX | **Image 设计规范文档修订（container-spec.md）**
  - 重写 `docs/impl-spec/deploy/image/container-spec.md`：新增「镜像构建」（多阶段 frontend-builder/deps/runtime）「镜像内目录布局」「workspace 挂载策略」节；重写「image 进程」节为 entrypoint.sh 编排（bash + wait -n + /dev/tcp 就绪探测）；「image expose port」仅 8000（删 9000）；修复「经典部署方法」`docker run -v` 参数位置 bug、`$your_domain` → `<your_domain>` 占位符、删注释段、`app_user_name` 加注释；新增 `openai_embedding_model` 字段说明
  - 修订 `root/.../everlingo.yaml` 模板：补 `openai_embedding_model: ''` 字段 + `interface: 0.0.0.0` 注释（容器部署有意为之）
  - `ARCHITECTURE.md` 新增「部署」节链接指向 container-spec.md
  - 决策汇总：进程编排 entrypoint.sh + wait -n；前端 Node 多阶段构建；运行时 python -m everlingo；build 期 uv sync + unidic download；镜内 /app/src + /app/web/dist WORKDIR /app；整目录挂载覆盖；日志写文件；保留 sudo；不加 HEALTHCHECK；indexer 就绪轮询 indexer.mcp.url + /dev/tcp；EVERLINGO_WORKSPACE_DIR env 设为 default workspace 路径
  - 创建 `docs/impl-spec/deploy/image/Dockerfile`：三阶段构建（frontend-builder/deps/runtime），runtime 阶段 `COPY docs/impl-spec/deploy/image/root/ /`（context=repo root）
  - 创建 `docs/impl-spec/deploy/image/root/app/entrypoint.sh`：bash + wait -n + /dev/tcp 就绪探测，统一 python -m everlingo 命令

- 2026-07-25 XX:XX | **Web Chatbot SSE 自动重连 + session_expired 处理**
  - `sseClient.ts`：`connectSSE` 重写，`onerror` 按 `readyState` 区分网络异常（`CONNECTING` → `scheduleRetry()`）与 session 过期（`CLOSED` → `session_expired`）；指数退避 1→2→4→8→16→30s 封顶；`onStatus` 回调通知 `connected`/`reconnecting` + 倒计时秒数 / `session_expired`；暴露 `retryNow()`
  - `ChatWindow.tsx`：`error` 拆分为 `connStatus`（连接）+ `error`（业务）；amber 色提示条在 `reconnecting` 时显示倒计时及「立即重试」按钮，`session_expired` 时显示「会话已过期 [重新开始]」；`handleRebuild` 创建新 session + 插入系统消息；`reconnectNonce` 触发 useEffect 重跑；正常/重连成功不显示；非连接错误保持红色 banner
  - `MessageBubble.tsx` + `types/chat.ts`：增加 `from: 'system'` 类型，渲染为居中灰色文本
  - `docs/impl-spec/web-chatbot.md` 新增「SSE 自动重连」小节，含 `session_expired` 分支
- 2026-07-25 XX:XX | **Web Chatbot 移动端响应式适配**
  - 断点 `md` (768px)：所有响应式差异用 `md:` 前缀表达，纯 CSS 方案
  - 按钮文字用 `<span className="hidden md:inline">` 包裹，移动端仅显示图标（笔记编辑器、发送）
  - 「发送」按钮移动端缩小为方形 icon button（`w-9` + `aria-label`）
  - 容器 padding/border 响应式：`ChatWindow` 根 `px-0 md:px-6`、header/messages/input padding 收紧
  - `TaskSelector` 纯文字按钮保持不动
  - 更新 `docs/impl-spec/web-chatbot.md` 新增「移动端适配」一节
- 2026-07-24 XX:XX | **Vault Editor 移动端适配**
  - 断点 `md` (768px)：`< md` 移动端抽屉模式，`>= md` 桌面三栏 flex 不变
  - 按钮文字用 `<span className="hidden md:inline">` 包裹，移动端仅显示图标
  - Header 改 flex 布局，新增汉堡按钮（`Menu` 图标，`md:hidden`），toggle 左栏
  - 左栏/右栏 aside `< md` 时改为 `fixed` overlay + `translate-x` 滑入/滑出
  - 新增 backdrop（`z-30 bg-black/40`），点击关闭所有抽屉
  - 移动端抽屉互斥：打开一个自动关闭另一个
  - Resize 手柄加 `hidden md:block`，移动端隐藏
  - 新增 `useMediaQuery` hook（`matchMedia` + listener）
  - 更新 `docs/impl-spec/vault-editor.md` 移动端小节
- 2026-07-25 XX:XX | **为 Web Chatbot 与 Vault Editor 添加 favicon**
  - 源图 `docs/arts/chrome-icon.png` → `web/public/favicon.png`（Vite `public/` 部署）
  - `web/index.html` 与 `web/editor.html` 均添加 `<link rel="icon">`
  - 更新 `docs/impl-spec/web-chatbot.md` 与 `docs/impl-spec/vault-editor.md` 文档
- 2026-07-24 XX:XX | **最小化 frontmatter 必选字段 + slug 移出 frontmatter**
  - 方案 B：file_path 作 upsert 主键，ulid 列可空（SQLite UNIQUE 已允许多 NULL，无需 schema 迁移）
  - 代码：indexer._get_existing_rowid / sync.reconcile / watcher._dispatch 改按 file_path 查询
  - 新增 get_by_file_path()；ParsedDoc.ulid 改为 str | None
  - SearchHit.ulid 改为 str | None（protocol.py）
  - slug 移出 frontmatter：从文件名 `Path(rel).stem` 派生（frontmatter 有 slug 仍优先）
  - 移除 `"slug"` 从 _PROTECTED_FRONTMATTER_FIELDS 及相关 prompt
  - 更新 vault_spec.md / kb_items_spec_*.md / search-spec / agent.py / memory_writer_action.py 文档
  - 测试：missing-ulid 改成功 case；新增无 ulid index_file 测试、slug 从文件名派生测试
  - 影响范围：151 vault 搜索测试 + 50 writer agent 测试全部通过
