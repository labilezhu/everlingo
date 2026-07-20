# EverLingo Chrome Extension

记了么 —— 有记忆的 AI 外语老师。

## 开发

### 前提

- Node.js 18+
- EverLingo 后端在本地运行（端口 8000）

### 启动

```bash
# 1. 启动后端
cd /home/labile/everlingo
uv run gateway --channel_web

# 2. 构建 extension（watch 模式）
cd extension
npm run dev       # vite build --watch
```

### 加载扩展

1. 打开 `chrome://extensions`
2. 开启"开发者模式"
3. 点击"加载已解压的扩展程序"
4. 选择 `extension/dist` 目录
5. 点击扩展图标 → 在任意网页打开 sidecar

### 构建

```bash
cd extension
npm run build     # tsc + vite build
```

产物在 `extension/dist/`。

### 测试

```bash
npm test          # vitest run
```

## 配置

后端地址在 `src/config.ts` 中配置：

```ts
export const API_BASE_URL = 'http://localhost:8000';
```

生产部署前修改为线上地址。

## 验证流程

1. 启动 gateway
2. 加载 unpacked extension
3. 打开任意网页，选中一个词
4. 点击扩展图标 → sidecar 打开
5. sidecar 自动翻译选词
6. 输入文字追问，Agent 回复
7. 关闭 sidecar，20 分钟内重开 → UI history 恢复
8. 关闭 sidecar，21 分钟后重开 → 新建 session，UI 清空
