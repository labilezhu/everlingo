import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { detectBootstrapLang } from './detect';

describe('detectBootstrapLang', () => {
  const original = navigator.language;

  const setLang = (lang: string) => {
    Object.defineProperty(navigator, 'language', { configurable: true, value: lang });
  };

  afterEach(() => {
    Object.defineProperty(navigator, 'language', { configurable: true, value: original });
  });

  it('zh* → zh-CN', () => {
    setLang('zh-CN');
    expect(detectBootstrapLang()).toBe('zh-CN');
    setLang('zh');
    expect(detectBootstrapLang()).toBe('zh-CN');
    setLang('zh-TW');
    expect(detectBootstrapLang()).toBe('zh-CN');
  });

  it('en* → en', () => {
    setLang('en');
    expect(detectBootstrapLang()).toBe('en');
    setLang('en-US');
    expect(detectBootstrapLang()).toBe('en');
  });

  it('其它语言 → en 兜底', () => {
    setLang('ja-JP');
    expect(detectBootstrapLang()).toBe('en');
    setLang('fr-FR');
    expect(detectBootstrapLang()).toBe('en');
  });

  it('navigator 不存在时 → en', () => {
    vi.stubGlobal('navigator', undefined);
    expect(detectBootstrapLang()).toBe('en');
    vi.unstubAllGlobals();
  });
});