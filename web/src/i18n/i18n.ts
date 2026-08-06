// react-i18next 初始化与字典装配。
// ref: docs/ADR/20260806-phase3-web-i18n-onboarding.md §4.1
import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

import zhCommon from '@/locales/zh-CN/common.json';
import zhChatbot from '@/locales/zh-CN/chatbot.json';
import zhEditor from '@/locales/zh-CN/editor.json';
import zhMe from '@/locales/zh-CN/me.json';
import zhOnboarding from '@/locales/zh-CN/onboarding.json';
import zhWebConsole from '@/locales/zh-CN/web-console.json';
import zhLogin from '@/locales/zh-CN/login.json';
import zhSelfService from '@/locales/zh-CN/self-service.json';
import zhPat from '@/locales/zh-CN/pat.json';

import enCommon from '@/locales/en/common.json';
import enChatbot from '@/locales/en/chatbot.json';
import enEditor from '@/locales/en/editor.json';
import enMe from '@/locales/en/me.json';
import enOnboarding from '@/locales/en/onboarding.json';
import enWebConsole from '@/locales/en/web-console.json';
import enLogin from '@/locales/en/login.json';
import enSelfService from '@/locales/en/self-service.json';
import enPat from '@/locales/en/pat.json';

export const NS = [
  'common',
  'chatbot',
  'editor',
  'me',
  'onboarding',
  'web-console',
  'login',
  'self-service',
  'pat',
] as const;

export type Ns = (typeof NS)[number];

export const RESOURCES = {
  'zh-CN': {
    common: zhCommon,
    chatbot: zhChatbot,
    editor: zhEditor,
    me: zhMe,
    onboarding: zhOnboarding,
    'web-console': zhWebConsole,
    login: zhLogin,
    'self-service': zhSelfService,
    pat: zhPat,
  },
  en: {
    common: enCommon,
    chatbot: enChatbot,
    editor: enEditor,
    me: enMe,
    onboarding: enOnboarding,
    'web-console': enWebConsole,
    login: enLogin,
    'self-service': enSelfService,
    pat: enPat,
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

export function changeInterfaceLanguage(lang: string): Promise<unknown> {
  return i18n.changeLanguage(lang);
}

export { i18n };
