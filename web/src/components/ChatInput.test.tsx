import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { initI18n } from '@/i18n/i18n';
import ChatInput from './ChatInput';

vi.mock('@/services/sseClient', () => ({
  uploadImage: vi.fn(),
}));

vi.mock('@/lib/sha256', () => ({
  sha256Hex: vi.fn(async () => 'a'.repeat(64)),
}));

import { uploadImage } from '@/services/sseClient';

const mockUploadImage = uploadImage as unknown as ReturnType<typeof vi.fn>;

function getFileInput(container: HTMLElement): HTMLInputElement {
  const input = container.querySelector('input[type="file"]');
  if (!input) throw new Error('file input not found');
  return input as HTMLInputElement;
}

function makeImageFile(): File {
  return new File([new Uint8Array([1, 2, 3])], 'pic.png', { type: 'image/png' });
}

describe('ChatInput image upload', () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    await initI18n('zh-CN');
  });

  it('发送图片成功后 Send 按钮恢复可用', async () => {
    mockUploadImage.mockResolvedValue({ saved_resource_sha256: 'a'.repeat(64) });
    const onSend = vi.fn();
    const user = userEvent.setup();
    const { container } = render(<ChatInput onSend={onSend} disabled={false} pending={false} sessionId="s1" />);

    await user.upload(getFileInput(container), makeImageFile());
    await user.click(screen.getByRole('button', { name: '发送' }));

    await waitFor(() => {
      expect(onSend).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => {
      expect(screen.getByRole('button', { name: '发送' })).toBeEnabled();
    });
  });

  it('上传失败时显示错误且不调用 onSend，Send 按钮恢复可用', async () => {
    mockUploadImage.mockRejectedValue(new Error('boom'));
    const onSend = vi.fn();
    const user = userEvent.setup();
    const { container } = render(<ChatInput onSend={onSend} disabled={false} pending={false} sessionId="s1" />);

    await user.upload(getFileInput(container), makeImageFile());
    await user.click(screen.getByRole('button', { name: '发送' }));

    await waitFor(() => {
      expect(screen.getByText('图片上传失败')).toBeInTheDocument();
    });
    expect(onSend).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: '发送' })).toBeEnabled();
  });
});
