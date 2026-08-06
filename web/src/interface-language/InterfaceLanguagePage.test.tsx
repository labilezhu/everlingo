import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { i18n, initI18n } from '@/i18n/i18n';

vi.mock('@/services/apiFetch', () => ({
  apiFetch: vi.fn(),
  apiFetchJson: vi.fn(),
}));

vi.mock('@/i18n/bootstrap', () => ({
  changeInterfaceLanguage: vi.fn(),
}));

import { apiFetch, apiFetchJson } from '@/services/apiFetch';
import { changeInterfaceLanguage } from '@/i18n/bootstrap';
import InterfaceLanguagePage from './InterfaceLanguagePage';

const mockApiFetchJson = apiFetchJson as unknown as ReturnType<typeof vi.fn>;
const mockApiFetch = apiFetch as unknown as ReturnType<typeof vi.fn>;
const mockChangeLang = changeInterfaceLanguage as unknown as ReturnType<typeof vi.fn>;

const STATUS = {
  target_language: 'en',
  is_valid: true,
  vault_initialized: true,
  needs_setup: true,
  interface_language: '',
  interface_language_resolved: 'zh-CN',
  available_interface_languages: [
    { code: 'zh-CN', name: '简体中文' },
    { code: 'en', name: 'English' },
  ],
};

describe('InterfaceLanguagePage', () => {
  beforeEach(async () => {
    vi.resetAllMocks();
    await initI18n('zh-CN');
  });

  it('渲染可用界面语言列表', async () => {
    mockApiFetchJson.mockResolvedValue(STATUS);
    render(<InterfaceLanguagePage />);
    await waitFor(() => expect(screen.getByText('简体中文')).toBeInTheDocument());
    expect(screen.getByText('English')).toBeInTheDocument();
  });

  it('选择并保存后调用 POST + changeLanguage', async () => {
    mockApiFetchJson.mockResolvedValue(STATUS);
    mockApiFetch.mockResolvedValue({ ok: true, json: async () => ({}) });
    const user = userEvent.setup();
    render(<InterfaceLanguagePage />);
    await waitFor(() => expect(screen.getByText('English')).toBeInTheDocument());
    await user.click(screen.getByText('English'));
    await user.click(screen.getByRole('button', { name: /保存/ }));
    await waitFor(() => {
      expect(mockApiFetch).toHaveBeenCalledWith(
        '/api/user-profile/interface-language',
        expect.objectContaining({ method: 'POST' }),
      );
    });
    expect(mockChangeLang).toHaveBeenCalledWith('en');
  });

  it('保存失败显示错误文案', async () => {
    mockApiFetchJson.mockResolvedValue(STATUS);
    mockApiFetch.mockResolvedValue({ ok: false, json: async () => ({ detail: 'bad' }) });
    const user = userEvent.setup();
    render(<InterfaceLanguagePage />);
    await waitFor(() => expect(screen.getByText('简体中文')).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /保存/ }));
    await waitFor(() => expect(screen.getByText('bad')).toBeInTheDocument());
  });
});