// extension 启动引导：读取缓存的 interface_language 初始化 i18n。
// 语言优先级：chrome.storage.local 缓存的 interface_language（后端返回）→
// navigator 启发值。缓存值非法时回退启发值。
// ref: docs/i18n/i18n.md — Phase 4
import { initI18n } from './i18n';
import { resolveSupportedLang } from './detect';
import { getStoredInterfaceLanguage } from '@/config';

export async function bootstrapI18n(): Promise<void> {
  const stored = await getStoredInterfaceLanguage();
  const lang = resolveSupportedLang(stored);
  await initI18n(lang);
}

export { i18n } from './i18n';