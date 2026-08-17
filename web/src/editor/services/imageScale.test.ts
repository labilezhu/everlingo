import { describe, expect, it, vi, afterEach } from 'vitest';
import { shouldScale, scaleImageIfNeeded } from './imageScale';

function makeFile(): File {
  return new File([new Uint8Array([1, 2, 3])], 'big.png', { type: 'image/png' });
}

describe('shouldScale', () => {
  it('≤1920×1200 不缩放，超出缩放', () => {
    expect(shouldScale(1920, 1200)).toBe(false);
    expect(shouldScale(100, 100)).toBe(false);
    expect(shouldScale(1921, 1200)).toBe(true);
    expect(shouldScale(4000, 3000)).toBe(true);
  });
});

describe('scaleImageIfNeeded', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('无 createImageBitmap（非安全上下文）→ 返回 null 回退原图', async () => {
    const r = await scaleImageIfNeeded(makeFile());
    expect(r).toBeNull();
  });

  it('超限图片 → canvas 等比缩放并返回 Blob', async () => {
    const drawImage = vi.fn();
    const toBlob = vi.fn((cb: (b: Blob | null) => void) => cb(new Blob(['x'], { type: 'image/png' })));
    vi.stubGlobal('createImageBitmap', vi.fn(async () => ({ width: 4000, height: 3000, close: vi.fn() })));
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({ drawImage } as any);
    vi.spyOn(HTMLCanvasElement.prototype, 'toBlob').mockImplementation(toBlob as any);

    const r = await scaleImageIfNeeded(makeFile());
    expect(r).toBeInstanceOf(Blob);
    expect(drawImage).toHaveBeenCalledOnce();
  });

  it('限内图片 → 返回 null 且关闭 bitmap', async () => {
    const close = vi.fn();
    vi.stubGlobal('createImageBitmap', vi.fn(async () => ({ width: 640, height: 480, close })));
    const r = await scaleImageIfNeeded(makeFile());
    expect(r).toBeNull();
    expect(close).toHaveBeenCalledOnce();
  });

  it('createImageBitmap 失败 → 返回 null 回退原图', async () => {
    vi.stubGlobal('createImageBitmap', vi.fn(async () => { throw new Error('boom'); }));
    const r = await scaleImageIfNeeded(makeFile());
    expect(r).toBeNull();
  });

  it('canvas 2d context 不可用 → 返回 null', async () => {
    const close = vi.fn();
    vi.stubGlobal('createImageBitmap', vi.fn(async () => ({ width: 4000, height: 3000, close })));
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null);
    const r = await scaleImageIfNeeded(makeFile());
    expect(r).toBeNull();
    expect(close).toHaveBeenCalledOnce();
  });
});
