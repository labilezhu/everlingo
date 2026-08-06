import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { i18n } from './i18n';
import { bootstrapI18n, onboardingTarget } from './bootstrap';

vi.mock('@/services/apiFetch', () => ({
  apiFetchJson: vi.fn(),
}));

import { apiFetchJson } from '@/services/apiFetch';
import { detectBootstrapLang } from './detect';

const mockApiFetch = apiFetchJson as unknown as ReturnType<typeof vi.fn>;

describe('bootstrapI18n', () => {
  beforeEach(async () => {
    vi.resetAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('从服务端解析并切换语言', async () => {
    Object.defineProperty(navigator, 'language', { configurable: true, value: 'zh-CN' });
    mockApiFetch.mockResolvedValue({
      target_language: 'en',
      is_valid: true,
      vault_initialized: true,
      needs_setup: true,
      interface_language: 'en',
      interface_language_resolved: 'en',
      available_interface_languages: [{ code: 'zh-CN', name: '简体中文' }, { code: 'en', name: 'English' }],
    });
    const res = await bootstrapI18n();
    expect(i18n.language).toBe('en');
    expect(res.status?.interface_language_resolved).toBe('en');
  });

  it('路径为 /login 时跳过状态请求', async () => {
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: { pathname: '/login' },
    });
    const res = await bootstrapI18n();
    expect(mockApiFetch).not.toHaveBeenCalled();
    expect(res.status).toBeNull();
  });

  it('请求失败时沿用启发语言，不抛错', async () => {
    Object.defineProperty(navigator, 'language', { configurable: true, value: 'zh-CN' });
    mockApiFetch.mockRejectedValue(new Error('network'));
    const res = await bootstrapI18n();
    expect(i18n.language).toBe('zh-CN');
    expect(res.status).toBeNull();
  });
});

describe('onboardingTarget', () => {
  const base = {
    target_language: '',
    is_valid: false,
    vault_initialized: null,
    available_interface_languages: [],
  };

  it('needs_setup=false → null', () => {
    expect(onboardingTarget({ ...base, needs_setup: false, interface_language: '', interface_language_resolved: 'en' })).toBeNull();
  });

  it('needs_setup 且 interface_language 空 → step 1', () => {
    expect(onboardingTarget({ ...base, needs_setup: true, interface_language: '', interface_language_resolved: 'en' }))
      .toBe('/console/me/interface-language');
  });

  it('needs_setup 且 interface_language 已设 → step 2', () => {
    expect(onboardingTarget({ ...base, needs_setup: true, interface_language: 'zh-CN', interface_language_resolved: 'zh-CN' }))
      .toBe('/console/me/target-language');
  });
});