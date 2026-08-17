import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { initI18n } from '@/i18n/i18n';
import EditorApp from './EditorApp';

// jsdom 无 matchMedia，EditorApp 的 useMediaQuery 依赖它
if (typeof window !== 'undefined' && !window.matchMedia) {
  window.matchMedia = (query: string): MediaQueryList => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  });
}

const h = vi.hoisted(() => ({ insertSpy: vi.fn() }));

vi.mock('@/editor/services/vaultApi', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/editor/services/vaultApi')>();
  return {
    ...actual,
    listLangs: vi.fn(),
    tree: vi.fn(),
    read: vi.fn(),
    write: vi.fn(),
    uploadImage: vi.fn(),
  };
});

vi.mock('@/lib/sha256', () => ({
  sha256Hex: vi.fn(async () => 'a'.repeat(64)),
}));

vi.mock('@/editor/services/imageScale', () => ({
  scaleImageIfNeeded: vi.fn(async () => null),
}));

// 编辑器 mock：注册 insertImageRef，供断言「上传成功 → 调用插入」
vi.mock('@/editor/components/MilkdownEditor', async () => {
  const { createElement, useEffect } = await import('react');
  return {
    __esModule: true,
    default: (props: any) => {
      useEffect(() => {
        props.insertImageRef.current = h.insertSpy;
        return () => { props.insertImageRef.current = null; };
      }, [props.insertImageRef]);
      return createElement('div', { 'data-testid': 'milkdown-mock' });
    },
  };
});

vi.mock('@/editor/components/FileTree', async () => {
  const { createElement } = await import('react');
  return {
    __esModule: true,
    default: (props: any) =>
      createElement('button', { onClick: () => props.onSelect('items/vocab/hello-kitty.md') }, 'open'),
  };
});

vi.mock('@/editor/components/SearchBar', async () => {
  const { createElement } = await import('react');
  return { __esModule: true, default: () => createElement('div', null, 'search') };
});

vi.mock('@/components/ChatWindow', async () => {
  const { createElement } = await import('react');
  return { __esModule: true, default: () => createElement('div', null, 'chat') };
});

import { listLangs, tree, read, uploadImage } from '@/editor/services/vaultApi';

const mockListLangs = listLangs as unknown as ReturnType<typeof vi.fn>;
const mockTree = tree as unknown as ReturnType<typeof vi.fn>;
const mockRead = read as unknown as ReturnType<typeof vi.fn>;
const mockUploadImage = uploadImage as unknown as ReturnType<typeof vi.fn>;

const SHA = 'a'.repeat(64);

function getFileInput(container: HTMLElement): HTMLInputElement {
  const input = container.querySelector('input[type="file"]');
  if (!input) throw new Error('file input not found');
  return input as HTMLInputElement;
}

function makeImageFile(): File {
  return new File([new Uint8Array([1, 2, 3])], 'pic.png', { type: 'image/png' });
}

describe('EditorApp 插入图片', () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    h.insertSpy.mockClear();
    await initI18n('zh-CN');
    mockListLangs.mockResolvedValue({ vaults: ['en'], count: 1, default: 'en' });
    mockTree.mockResolvedValue({ path: '', depth: 2, entries: [] });
    mockRead.mockResolvedValue({ path: 'items/vocab/hello-kitty.md', content: '# hi', size_bytes: 4 });
    mockUploadImage.mockResolvedValue({
      src_resource_sha256: SHA,
      saved_resource_sha256: SHA,
      mime_type: 'image/png',
      size: 3,
      width: 1,
      height: 1,
      storage_key: 'k',
      created_at: '',
    });
  });

  it('上传成功 → uploadImage 以正确路径/内容被调，并触发编辑器插入（相对链接 + 绝对 URL）', async () => {
    const user = userEvent.setup();
    const { container } = render(<EditorApp />);

    // 打开文件（currentPath 就绪，sub-header 出现）
    await user.click(await screen.findByRole('button', { name: 'open' }));
    await screen.findByRole('button', { name: '插入图片' });

    const file = makeImageFile();
    await user.upload(getFileInput(container), file);

    await waitFor(() => {
      expect(mockUploadImage).toHaveBeenCalledTimes(1);
    });
    // sha 在 scale 之前计算（上传路径的 stem 即原始 sha）
    expect(mockUploadImage).toHaveBeenCalledWith(
      'en',
      `items/vocab/hello-kitty.assets/${SHA}.png`,
      file,
      'image/png',
    );

    await waitFor(() => {
      expect(h.insertSpy).toHaveBeenCalledWith(
        `hello-kitty.assets/${SHA}.png`,
        `/api/vault/raw/en/items/vocab/hello-kitty.assets/${SHA}.png`,
        'hello-kitty',
      );
    });
  });

  it('未打开文件时不渲染插入按钮', async () => {
    const user = userEvent.setup();
    render(<EditorApp />);
    expect(screen.queryByRole('button', { name: '插入图片' })).not.toBeInTheDocument();
  });

  it('上传失败 → 显示错误信息且不触发插入', async () => {
    mockUploadImage.mockRejectedValue(new Error('sha256 mismatch'));
    const user = userEvent.setup();
    const { container } = render(<EditorApp />);

    await user.click(await screen.findByRole('button', { name: 'open' }));
    await screen.findByRole('button', { name: '插入图片' });

    await user.upload(getFileInput(container), makeImageFile());

    await waitFor(() => {
      expect(screen.getByText(/图片上传失败/)).toBeInTheDocument();
    });
    expect(h.insertSpy).not.toHaveBeenCalled();
  });
});
