import { describe, expect, it } from 'vitest';
import { RESOURCES, NS } from '@/i18n/i18n';

function flattenKeys(obj: Record<string, unknown>, prefix = ''): string[] {
  const keys: string[] = [];
  for (const [k, v] of Object.entries(obj)) {
    const path = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === 'object') {
      keys.push(...flattenKeys(v as Record<string, unknown>, path));
    } else {
      keys.push(path);
    }
  }
  return keys;
}

describe('i18n 字典一致性', () => {
  it('两种语言的 namespace 集合一致', () => {
    expect(Object.keys(RESOURCES['zh-CN']).sort()).toEqual(NS.slice().sort());
    expect(Object.keys(RESOURCES['en']).sort()).toEqual(NS.slice().sort());
  });

  it('每种语言下所有 namespace 存在且为非空对象', () => {
    for (const lang of Object.keys(RESOURCES)) {
      for (const ns of NS) {
        const dict = RESOURCES[lang as keyof typeof RESOURCES][ns];
        expect(dict, `${lang}/${ns}`).toBeTypeOf('object');
        expect(Object.keys(dict).length, `${lang}/${ns}`).toBeGreaterThan(0);
      }
    }
  });

  it('zh-CN 与 en 的 key 集合完全相等（防漂移）', () => {
    for (const ns of NS) {
      const zhKeys = flattenKeys(RESOURCES['zh-CN'][ns]).sort();
      const enKeys = flattenKeys(RESOURCES['en'][ns]).sort();
      expect(zhKeys, `ns=${ns} zh keys`).toEqual(enKeys);
    }
  });

  it('占位符 {{x}} 在两种语言中一致', () => {
    const extract = (v: string): string[] => [...v.matchAll(/\{\{(\w+)\}\}/g)].map(m => m[1]).sort();
    for (const ns of NS) {
      for (const key of flattenKeys(RESOURCES['zh-CN'][ns])) {
        const zhVal = getValue(RESOURCES['zh-CN'][ns], key) as string;
        const enVal = getValue(RESOURCES['en'][ns], key) as string;
        if (typeof zhVal === 'string' && typeof enVal === 'string') {
          expect(extract(zhVal), `ns=${ns} key=${key}`).toEqual(extract(enVal));
        }
      }
    }
  });
});

function getValue(obj: Record<string, unknown>, path: string): unknown {
  return path.split('.').reduce<unknown>((acc, part) => (acc as Record<string, unknown>)?.[part], obj);
}