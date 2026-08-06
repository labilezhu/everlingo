// 首屏加载占位语言启发式推断（仅用于 i18n.changeLanguage 完成前的过渡文案）。
// 不写持久化存储；最终生效值以服务端 interface_language_resolved 为准。
// ref: docs/ADR/20260806-phase3-web-i18n-onboarding.md §4.2
export function detectBootstrapLang(): string {
  const nav = (typeof navigator !== 'undefined' ? navigator.language : '') || 'en';
  const normalized = nav.toLowerCase();
  if (normalized.startsWith('zh')) return 'zh-CN';
  return 'en';
}
