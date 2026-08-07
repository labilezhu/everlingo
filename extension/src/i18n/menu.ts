// 右键菜单文案（background service worker，非 React 上下文，不引入 react-i18next）。
// ref: docs/i18n/i18n.md — Phase 4

export const CONTEXT_MENU_TITLES: Record<string, string> = {
  'zh-CN': '用小记🐹翻译',
  en: 'Translate with Nori🐹',
};

export function contextMenuTitle(lang: string): string {
  return CONTEXT_MENU_TITLES[lang] ?? CONTEXT_MENU_TITLES.en;
}