// 界面语言推断与归一化（Chrome Extension）。
// 与 web/src/i18n/detect.ts 语义一致，但 extension 语言来源是 chrome.storage.local
// 缓存的 interface_language（创建 session 时后端返回），此处仅为兜底与校验。
// ref: docs/i18n/i18n.md — Phase 4

export const AVAILABLE_INTERFACE_LANGUAGES = ['zh-CN', 'en'] as const;

export function detectBootstrapLang(): string {
  const nav = (typeof navigator !== 'undefined' ? navigator.language : '') || 'en';
  if (nav.toLowerCase().startsWith('zh')) return 'zh-CN';
  return 'en';
}

export function resolveSupportedLang(lang: string | undefined | null): string {
  if (lang === 'zh-CN' || lang === 'en') return lang;
  return detectBootstrapLang();
}