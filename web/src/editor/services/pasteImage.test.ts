import { describe, expect, it } from 'vitest';
import { extractImageFile } from './pasteImage';

function makeFile(name: string, type: string): File {
  return new File([new Uint8Array([1])], name, { type });
}

function item(kind: string, type: string, file?: File) {
  return {
    kind,
    type,
    getAsFile: () => file ?? null,
  };
}

function makeDataTransfer(items: Array<{ kind: string; type: string; getAsFile: () => File | null }>): DataTransfer {
  // jsdom 不实现 DataTransfer.items，用 cast 的最小桩模拟
  return { items } as unknown as DataTransfer;
}

describe('extractImageFile', () => {
  it('命中 png 图片文件', () => {
    const f = makeFile('a.png', 'image/png');
    expect(extractImageFile(makeDataTransfer([item('file', 'image/png', f)]))).toBe(f);
  });

  it('命中最先出现的图片 item（多 item 取首个）', () => {
    const png = makeFile('a.png', 'image/png');
    const jpg = makeFile('b.jpg', 'image/jpeg');
    expect(extractImageFile(makeDataTransfer([item('string', 'text/plain'), item('file', 'image/jpeg', jpg), item('file', 'image/png', png)]))).toBe(jpg);
  });

  it('非图片（纯文本粘贴）返回 null，不拦截', () => {
    expect(extractImageFile(makeDataTransfer([item('string', 'text/plain')]))).toBeNull();
  });

  it('不支持的类型（gif）返回 null', () => {
    const f = makeFile('a.gif', 'image/gif');
    expect(extractImageFile(makeDataTransfer([item('file', 'image/gif', f)]))).toBeNull();
  });

  it('clipboardData 为 null 时返回 null', () => {
    expect(extractImageFile(null)).toBeNull();
  });

  it('getAsFile 返回 null 时跳过', () => {
    expect(extractImageFile(makeDataTransfer([item('file', 'image/png')]))).toBeNull();
  });
});