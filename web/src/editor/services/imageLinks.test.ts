import { describe, expect, it } from 'vitest';
import {
  toDisplay,
  toRelative,
  buildUploadPath,
  dirname,
  relPath,
  normalizeVaultPath,
  mdNameFromPath,
  extFromMime,
} from './imageLinks';

const lang = 'en';
const currentPath = 'items/vocab/hello-kitty.md';
const SHA = '2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1d0f';

describe('imageLinks 路径工具', () => {
  it('dirname', () => {
    expect(dirname('items/vocab/hello.md')).toBe('items/vocab');
    expect(dirname('hello.md')).toBe('');
  });

  it('mdNameFromPath', () => {
    expect(mdNameFromPath('items/vocab/hello-kitty.md')).toBe('hello-kitty');
    expect(mdNameFromPath('hello.MD')).toBe('hello');
    expect(mdNameFromPath('noext')).toBe('noext');
  });

  it('normalizeVaultPath 处理 ./ ../', () => {
    expect(normalizeVaultPath(['items', 'vocab', '.', 'x', '..', 'hello-kitty.assets', 'a.png']))
      .toBe('items/vocab/hello-kitty.assets/a.png');
    // 越出 vault 根的前导 ../ 被丢弃
    expect(normalizeVaultPath(['..', '..', 'events'])).toBe('events');
    // 中段 ../ 回退上一级
    expect(normalizeVaultPath(['items', 'vocab', '..', 'events'])).toBe('items/events');
  });

  it('relPath', () => {
    expect(relPath('items/vocab', 'items/vocab/hello-kitty.assets/a.png')).toBe('hello-kitty.assets/a.png');
    expect(relPath('items/vocab', 'events/2026/a.png')).toBe('../../events/2026/a.png');
    expect(relPath('', 'events/a.png')).toBe('events/a.png');
  });

  it('extFromMime', () => {
    expect(extFromMime('image/jpeg')).toBe('jpg');
    expect(extFromMime('image/png')).toBe('png');
    expect(extFromMime('image/webp')).toBe('webp');
    expect(extFromMime('image/gif')).toBe('png');
  });

  it('buildUploadPath 嵌套文件', () => {
    expect(buildUploadPath('items/vocab/hello-kitty.md', SHA, 'png')).toEqual({
      vaultRelPath: `items/vocab/hello-kitty.assets/${SHA}.png`,
      rel: `hello-kitty.assets/${SHA}.png`,
    });
  });

  it('buildUploadPath 根目录文件', () => {
    expect(buildUploadPath('hello.md', SHA, 'jpg')).toEqual({
      vaultRelPath: `hello.assets/${SHA}.jpg`,
      rel: `hello.assets/${SHA}.jpg`,
    });
  });
});

describe('toDisplay（相对 → 绝对 API URL）', () => {
  it('相对链接解析为绝对 URL', () => {
    const md = `![cat](hello-kitty.assets/${SHA}.png)`;
    expect(toDisplay(lang, currentPath, md))
      .toBe(`![cat](/api/vault/raw/en/items/vocab/hello-kitty.assets/${SHA}.png)`);
  });

  it('../ 相对导航', () => {
    const md = '![a](../events/2026/x.png)';
    // items/vocab/../events → items/events
    expect(toDisplay(lang, 'items/vocab/hello.md', md))
      .toBe('![a](/api/vault/raw/en/items/events/2026/x.png)');
  });

  it('/ 开头按 vault 根解析', () => {
    const md = '![a](/events/x.png)';
    expect(toDisplay(lang, currentPath, md)).toBe('![a](/api/vault/raw/en/events/x.png)');
  });

  it('外链 / data URI / 已是绝对 URL 原样保留', () => {
    const external = '![a](https://example.com/a.png)';
    const data = '![a](data:image/png;base64,iVBORw0KGgo=)';
    const already = `![a](/api/vault/raw/en/items/vocab/${SHA}.png)`;
    expect(toDisplay(lang, currentPath, external)).toBe(external);
    expect(toDisplay(lang, currentPath, data)).toBe(data);
    expect(toDisplay(lang, currentPath, already)).toBe(already);
  });

  it('保留 alt 与 title', () => {
    const md = '![my cat](hello-kitty.assets/a.png "hello kitty")';
    expect(toDisplay(lang, currentPath, md))
      .toBe('![my cat](/api/vault/raw/en/items/vocab/hello-kitty.assets/a.png "hello kitty")');
  });

  it('非图片 markdown 不受影响', () => {
    const md = '[link](/items/god.md) **bold** ![a](x.png) `code`';
    expect(toDisplay(lang, currentPath, md))
      .toBe('[link](/items/god.md) **bold** ![a](/api/vault/raw/en/items/vocab/x.png) `code`');
  });
});

describe('toRelative（绝对 API URL → 相对）', () => {
  it('绝对 URL 改写为相对路径', () => {
    const md = `![cat](/api/vault/raw/en/items/vocab/hello-kitty.assets/${SHA}.png)`;
    expect(toRelative(lang, currentPath, md))
      .toBe(`![cat](hello-kitty.assets/${SHA}.png)`);
  });

  it('../ 形态', () => {
    const md = '![a](/api/vault/raw/en/events/2026/x.png)';
    expect(toRelative(lang, 'items/vocab/hello.md', md))
      .toBe('![a](../../events/2026/x.png)');
  });

  it('不同 lang / 外链 / 相对链接原样保留', () => {
    const otherLang = '![a](/api/vault/raw/fr/items/x.png)';
    const external = '![a](https://example.com/a.png)';
    const relForm = '![a](hello-kitty.assets/a.png)';
    expect(toRelative(lang, currentPath, otherLang)).toBe(otherLang);
    expect(toRelative(lang, currentPath, external)).toBe(external);
    expect(toRelative(lang, currentPath, relForm)).toBe(relForm);
  });

  it('路径含空格（%20）解码后以 <> 包裹', () => {
    const md = '![a](/api/vault/raw/en/items/vocab/hello.assets/my%20pic.png)';
    expect(toRelative(lang, 'items/vocab/hello.md', md))
      .toBe('![a](<hello.assets/my pic.png>)');
  });
});

describe('往返不变式', () => {
  const display = `![cat](/api/vault/raw/en/items/vocab/hello-kitty.assets/${SHA}.png)`;
  const rel = `![cat](hello-kitty.assets/${SHA}.png)`;

  it('display → relative → display', () => {
    expect(toDisplay(lang, currentPath, toRelative(lang, currentPath, display))).toBe(display);
  });

  it('relative → display → relative', () => {
    expect(toRelative(lang, currentPath, toDisplay(lang, currentPath, rel))).toBe(rel);
  });

  it('多图混排往返稳定', () => {
    const doc = `# title

![a](../events/x.png) text ![b](hello-kitty.assets/b.png "t")

> ![c](/assets/c.png)
`;
    const displayDoc = toDisplay(lang, currentPath, doc);
    const relDoc = toRelative(lang, currentPath, displayDoc);
    // 绝对 ↔ 相对互为逆变换（对相对形态再 toDisplay 应还原 displayDoc）
    expect(toDisplay(lang, currentPath, relDoc)).toBe(displayDoc);
    // 相对形态：均相对当前 md 目录（/assets/c.png 等价归一为 ../../assets/c.png）
    expect(relDoc).toContain('![a](../events/x.png)');
    expect(relDoc).toContain('![b](hello-kitty.assets/b.png "t")');
    expect(relDoc).toContain('![c](../../assets/c.png)');
  });
});
