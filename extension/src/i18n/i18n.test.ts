// i18n 资源一致性 + 语言解析测试（extension）。
// ref: docs/i18n/i18n.md — Phase 4
import { describe, it, expect } from 'vitest';
import { RESOURCES } from './i18n';
import { detectBootstrapLang, resolveSupportedLang, AVAILABLE_INTERFACE_LANGUAGES } from './detect';
import { CONTEXT_MENU_TITLES, contextMenuTitle } from './menu';

const resources = RESOURCES as unknown as Record<string, Record<string, Record<string, unknown>>>;

function keysOf(obj: Record<string, unknown>): string[] {
  return Object.keys(obj).sort();
}

function flattenKeys(ns: Record<string, unknown>, prefix = ''): string[] {
  const out: string[] = [];
  for (const [k, v] of Object.entries(ns)) {
    const key = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === 'object' && !Array.isArray(v)) {
      out.push(...flattenKeys(v as Record<string, unknown>, key));
    } else {
      out.push(key);
    }
  }
  return out;
}

const LANGUAGES = ['zh-CN', 'en'];
const NS = Object.keys(resources['zh-CN']);

describe('i18n resource consistency', () => {
  it('dimensiona zh-CN 与 en 语言都覆盖了全部 namespace', () => {
    for (const lang of LANGUAGES) {
      for (const ns of NS) {
        expect(resources[lang]).toHaveProperty(ns);
      }
    }
  });

  it('每个 namespace 的 zh-CN / en key 集合深度一致', () => {
    for (const ns of NS) {
      const zhFlattened = flattenKeys(resources['zh-CN'][ns]);
      const enFlattened = flattenKeys(resources['en'][ns]);
      expect(zhFlattened.sort(), `ns=${ns}`).toEqual(enFlattened.sort());
    }
  });

  it('reconnecting 占位符 {{count}} 在两种语言中一致', () => {
    const zh = resources['zh-CN'].chatbot as Record<string, string>;
    const en = resources['en'].chatbot as Record<string, string>;
    expect(zh['reconnecting']).toContain('{{count}}');
    expect(en['reconnecting']).toContain('{{count}}');
  });

  it('每次 zone 高亮个 placeholder 占位符一致（含 options.bad_status）', () => {
    const zhOpt = resources['zh-CN'].options as Record<string, string>;
    const enOpt = resources['en'].options as Record<string, string>;
    for (const k of Object.keys(zhOpt)) {
      if (typeof zhOpt[k] !== 'string') continue;
      const zhTokens = zhOpt[k].match(/\{\{.*?\}\}/g) ?? [];
      const enTokens = enOpt[k].match(/\{\{.*?\}\}/g) ?? [];
      expect(zhTokens).toEqual(enTokens);
    }
  });
});

describe('detect / resolveSupportedLang', () => {
  it('AVAILABLE_INTERFACE_LANGUAGES 恰好为 zh-CN、en', () => {
    expect(AVAILABLE_INTERFACE_LANGUAGES).toEqual(['zh-CN', 'en']);
  });

  it('合法值原样返回', () => {
    expect(resolveSupportedLang('zh-CN')).toBe('zh-CN');
    expect(resolveSupportedLang('en')).toBe('en');
  });

  it('空/null/不支持的都回退到 detectBootstrapLang()', () => {
    expect(resolveSupportedLang('')).toBe(detectBootstrapLang());
    expect(resolveSupportedLang(null)).toBe(detectBootstrapLang());
    expect(resolveSupportedLang('fr')).toBe(detectBootstrapLang());
    expect(resolveSupportedLang(undefined)).toBe(detectBootstrapLang());
  });
});

describe('context menu', () => {
  it('zh-CN 与 en 都有目录文案', () => {
    expect(CONTEXT_MENU_TITLES).toHaveProperty('zh-CN');
    expect(CONTEXT_MENU_TITLES).toHaveProperty('en');
  });

  it('未知语言回退 en', () => {
    expect(contextMenuTitle('fr')).toBe(CONTEXT_MENU_TITLES.en);
    expect(contextMenuTitle('zh-CN')).toBe(CONTEXT_MENU_TITLES['zh-CN']);
  });
});