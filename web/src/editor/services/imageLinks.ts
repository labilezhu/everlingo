import { assetUrl } from './vaultApi';

// ref: docs/ADR/20260816-markdown-image.md — 决策 1 / 决策 2
// markdown 保存相对路径；WYSIWYG 预览改写为绝对 API URL（/api/vault/raw/{lang}/{path}）。
// 本模块集中所有「图片链接相对↔绝对」改写逻辑，纯函数、可单测。
// 已知限制：URL 含 ')' 且未用 <...> 包裹的 token 无法正确切分（罕见，暂不支持）。

const RAW_PREFIX = '/api/vault/raw';

// ── 路径工具 ───────────────────────────────────────────────

export function dirname(path: string): string {
  const i = path.lastIndexOf('/');
  return i >= 0 ? path.slice(0, i) : '';
}

export function mdNameFromPath(path: string): string {
  const base = path.slice(path.lastIndexOf('/') + 1);
  return base.replace(/\.md$/i, '') || base;
}

/** 规范化 vault 路径段（处理 ./ ../ 空段），返回无前导/尾随斜杠的相对路径。 */
export function normalizeVaultPath(parts: string[]): string {
  const result: string[] = [];
  for (const part of parts) {
    if (part === '' || part === '.') continue;
    if (part === '..') {
      if (result.length > 0) result.pop();
      continue;
    }
    result.push(part);
  }
  return result.join('/');
}

/** 从 fromDir（vault 相对目录，可空）到 toPath（vault 相对路径）的相对路径。 */
export function relPath(fromDir: string, toPath: string): string {
  const fromSegs = fromDir ? fromDir.split('/') : [];
  const toSegs = toPath.split('/');
  let i = 0;
  while (i < fromSegs.length && i < toSegs.length && fromSegs[i] === toSegs[i]) i++;
  const up = fromSegs.length - i;
  const rest = toSegs.slice(i);
  return [...new Array(up).fill('..'), ...rest].join('/');
}

export function extFromMime(mime: string): string {
  switch (mime) {
    case 'image/jpeg': return 'jpg';
    case 'image/webp': return 'webp';
    case 'image/png': return 'png';
    default: return 'png';
  }
}

/** 由当前 md 文件路径构造默认上传路径（ADR 决策 2：{md_dir}/{mdname}.assets/{sha}.{ext}）。 */
export function buildUploadPath(
  currentPath: string,
  srcSha: string,
  ext: string,
): { vaultRelPath: string; rel: string } {
  const mdDir = dirname(currentPath);
  const mdName = mdNameFromPath(currentPath);
  const rel = `${mdName}.assets/${srcSha}.${ext}`;
  const vaultRelPath = mdDir ? `${mdDir}/${rel}` : rel;
  return { vaultRelPath, rel };
}

// ── markdown 图片 token ────────────────────────────────────

const IMAGE_TOKEN_RE = /!\[[^\]]*\]\([^)]*\)/g;

interface ParsedImageToken {
  alt: string;
  url: string;
  titleSuffix: string;
}

/** 解析 ![alt](<url> "title")，返回 url（去 <>）与 title 后缀。解析失败返回 null。 */
function parseImageToken(token: string): ParsedImageToken | null {
  const m = /^!\[([^\]]*)\]\(([^)]*)\)$/.exec(token);
  if (!m) return null;
  const alt = m[1];
  let inner = m[2].trim();
  let url = inner;
  let titleSuffix = '';
  if (inner.startsWith('<')) {
    const close = inner.indexOf('>');
    if (close >= 0) {
      url = inner.slice(1, close);
      const rest = inner.slice(close + 1).trim();
      if (rest) titleSuffix = ` ${rest}`;
    }
  } else {
    const sp = inner.search(/\s/);
    if (sp >= 0) {
      url = inner.slice(0, sp);
      const rest = inner.slice(sp).trim();
      if (rest) titleSuffix = ` ${rest}`;
    }
  }
  return { alt, url, titleSuffix };
}

/** URL 含空白时用 <...> 包裹（markdown 合法形态），否则原样。 */
function formatLinkUrl(url: string): string {
  return /\s/.test(url) ? `<${url}>` : url;
}

function renderImageToken(alt: string, url: string, titleSuffix: string): string {
  return `![${alt}](${formatLinkUrl(url)}${titleSuffix})`;
}

/** 是否为浏览器可直接解析、不需改写的链接（带 scheme 或已是 display URL）。 */
function isExternalOrDisplay(link: string): boolean {
  if (link.startsWith(RAW_PREFIX)) return true;
  return /^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(link);
}

// ── 显示（相对 → 绝对 API URL）──────────────────────────────

function linkToDisplayUrl(lang: string, dir: string, link: string): string | null {
  if (isExternalOrDisplay(link)) return null;
  let resolved: string;
  if (link.startsWith('/')) {
    resolved = normalizeVaultPath(link.slice(1).split('/'));
  } else {
    const segs = dir ? dir.split('/') : [];
    resolved = normalizeVaultPath([...segs, ...link.split('/')]);
  }
  if (!resolved) return null;
  return assetUrl(lang, resolved);
}

export function toDisplay(lang: string, currentPath: string, md: string): string {
  const dir = dirname(currentPath);
  return md.replace(IMAGE_TOKEN_RE, (token) => {
    const parsed = parseImageToken(token);
    if (!parsed) return token;
    const displayUrl = linkToDisplayUrl(lang, dir, parsed.url.trim());
    if (displayUrl === null) return token;
    return renderImageToken(parsed.alt, displayUrl, parsed.titleSuffix);
  });
}

// ── 相对（绝对 API URL → 相对当前 md 目录）─────────────────

function displayUrlToVaultPath(lang: string, link: string): string | null {
  if (!link.startsWith(RAW_PREFIX)) return null;
  const rest = link.slice(RAW_PREFIX.length).replace(/^\/+/, '');
  const segs = rest.split('/');
  if (segs.length < 2) return null;
  const [rawLang, ...pathSegs] = segs;
  let langDecoded: string;
  try {
    langDecoded = decodeURIComponent(rawLang);
  } catch {
    return null;
  }
  if (langDecoded !== lang) return null;
  let decoded: string[];
  try {
    decoded = pathSegs.map(decodeURIComponent);
  } catch {
    return null;
  }
  const resolved = normalizeVaultPath(decoded);
  return resolved || null;
}

export function toRelative(lang: string, currentPath: string, md: string): string {
  const dir = dirname(currentPath);
  return md.replace(IMAGE_TOKEN_RE, (token) => {
    const parsed = parseImageToken(token);
    if (!parsed) return token;
    const vaultPath = displayUrlToVaultPath(lang, parsed.url.trim());
    if (vaultPath === null) return token;
    return renderImageToken(parsed.alt, relPath(dir, vaultPath), parsed.titleSuffix);
  });
}
