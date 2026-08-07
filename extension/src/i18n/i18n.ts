// react-i18next 初始化与字典装配（Chrome Extension）。
// extension 仅使用 common / chatbot / options 三个 namespace：
// - common / chatbot：与 web 端同源同 key（复制自 web/src/locales/）
// - options：extension 独有（OptionsForm 设置页），无 web 对应
// ref: docs/i18n/i18n.md — Phase 4
import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

import zhCommon from '@/locales/zh-CN/common.json';
import zhChatbot from '@/locales/zh-CN/chatbot.json';
import zhOptions from '@/locales/zh-CN/options.json';

import enCommon from '@/locales/en/common.json';
import enChatbot from '@/locales/en/chatbot.json';
import enOptions from '@/locales/en/options.json';

export const NS = ['common', 'chatbot', 'options'] as const;

export type Ns = (typeof NS)[number];

export const RESOURCES = {
  'zh-CN': {
    common: zhCommon,
    chatbot: zhChatbot,
    options: zhOptions,
  },
  en: {
    common: enCommon,
    chatbot: enChatbot,
    options: enOptions,
  },
} as const;

export async function initI18n(lang: string): Promise<typeof i18n> {
  await i18n.use(initReactI18next).init({
    resources: RESOURCES,
    lng: lang,
    fallbackLng: 'en',
    defaultNS: 'common',
    ns: NS,
    interpolation: { escapeValue: false },
    returnEmptyString: false,
  });
  return i18n;
}

export { i18n };