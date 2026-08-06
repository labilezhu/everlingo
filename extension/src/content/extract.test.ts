import { describe, it, expect, afterEach } from 'vitest';
import { centerWindow, extractContextText } from './extract';

// --------------------------------------------------------------------------
// 纯函数 centerWindow：以选词为中心截取窗口的回归测试（无需 DOM）
// --------------------------------------------------------------------------

describe('centerWindow', () => {
  it('returns sourceText unchanged when it fits within maxLen', () => {
    const src = 'I sat on the bank of the river.';
    expect(centerWindow(src, 'bank', 14)).toBe(src);
  });

  it('returns empty string for empty sourceText', () => {
    expect(centerWindow('', '', 0)).toBe('');
  });

  it('centers the window around the selection in the middle', () => {
    const src = 'A'.repeat(300) + 'target' + 'B'.repeat(590); // length 600
    const maxLen = 100;
    const selStart = 300;
    const result = centerWindow(src, 'target', selStart, maxLen);
    expect(result.length).toBe(maxLen);
    const selLen = 6;
    const expectedStart = Math.max(0, selStart - Math.floor((maxLen - selLen) / 2));
    expect(result).toBe(src.slice(expectedStart, expectedStart + maxLen));
  });

  it('starts window at 0 when selection is near the beginning', () => {
    const src = 'X'.repeat(600);
    const result = centerWindow(src, 'XX', 2, 100);
    expect(result).toBe('X'.repeat(100));
  });

  it('right-aligns the window when selection is near the end', () => {
    const src = 'A'.repeat(560) + 'target' + 'B'.repeat(34); // length 600, target at 560
    const maxLen = 100;
    const selStart = 560;
    const result = centerWindow(src, 'target', selStart, maxLen);
    expect(result.length).toBe(maxLen);
    expect(result).toBe(src.slice(src.length - maxLen));
  });

  it('falls back to head truncation when selectedText is empty', () => {
    const src = 'A'.repeat(600);
    const result = centerWindow(src, '', 0, 100);
    expect(result).toBe('A'.repeat(100));
  });

  it('caps selLen at maxLen without crashing', () => {
    const src = 'A'.repeat(600);
    const selectedText = 'B'.repeat(600);
    const result = centerWindow(src, selectedText, 50, 100);
    expect(result.length).toBe(100);
  });
});

// --------------------------------------------------------------------------
// extractContextText：极简 DOM mock，验证 textContentOffset 偏移计算。
// 覆盖"选词落在长段落中段"、"跨嵌套内联元素偏移不错位"、"选词靠末尾右靠"。
// --------------------------------------------------------------------------

type MockNode = MockElement | MockTextNode;

interface MockTextNode {
  nodeType: 3;
  data: string;
  textContent: string;
  parentElement: MockElement | null;
  parentNode: MockElement | null;
}

interface MockElement {
  nodeType: 1;
  tagName: string;
  textContent: string;
  childNodes: MockNode[];
  parentElement: MockElement | null;
  parentNode: MockElement | null;
}

interface MockRange {
  commonAncestorContainer: MockElement | MockTextNode;
  startContainer: MockTextNode | MockElement;
  startOffset: number;
}

interface MockSelection {
  rangeCount: number;
  getRangeAt: () => MockRange;
  toString: () => string;
}

const TEXT_NODE = 3;
const ELEMENT_NODE = 1;

function makeText(data: string): MockTextNode {
  return { nodeType: TEXT_NODE, data, textContent: data, parentElement: null, parentNode: null };
}

function makeElement(tagName: string, children: MockNode[]): MockElement {
  const textOf = (n: MockNode): string =>
    n.nodeType === TEXT_NODE ? (n as MockTextNode).data : (n as MockElement).textContent;
  const el: MockElement = {
    nodeType: ELEMENT_NODE,
    tagName,
    textContent: children.map(textOf).join(''),
    childNodes: children,
    parentElement: null,
    parentNode: null,
  };
  for (const c of children) {
    (c as MockElement).parentElement = el;
    (c as MockElement).parentNode = el;
  }
  return el;
}

function collectTexts(root: MockNode): MockTextNode[] {
  const out: MockTextNode[] = [];
  const walk = (n: MockNode) => {
    if (n.nodeType === TEXT_NODE) {
      out.push(n as MockTextNode);
    } else {
      for (const c of (n as MockElement).childNodes) walk(c);
    }
  };
  walk(root);
  return out;
}

function installDocument(root: MockElement) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (globalThis as any).document = {
    body: { textContent: '' },
    createTreeWalker: (r: MockElement) => {
      const nodes = collectTexts(r);
      let i = 0;
      return { nextNode: () => (i < nodes.length ? nodes[i++]! : null) };
    },
  };
}

function cleanupDocument() {
  delete (globalThis as { document?: unknown }).document;
}

// 返回替身 Selection，并 cast 成真实 Selection 供 extractContextText 消费。
function makeSelection(
  block: MockElement,
  startContainer: MockTextNode | MockElement,
  startOffset: number,
  selectedText: string,
): Selection {
  const s: MockSelection = {
    rangeCount: 1,
    getRangeAt: () => ({ commonAncestorContainer: block, startContainer, startOffset }),
    toString: () => selectedText,
  };
  return s as unknown as Selection;
}

describe('extractContextText', () => {
  afterEach(cleanupDocument);

  it('centers the window around a selection in the middle of a long paragraph', () => {
    const p = makeElement('P', [makeText('A'.repeat(300) + 'ZZZZ' + 'B'.repeat(294))]); // length 598
    installDocument(p);
    const textNode = p.childNodes[0] as MockTextNode;
    const result = extractContextText(makeSelection(p, textNode, 300, 'ZZZZ'));

    expect(result.length).toBe(500);
    expect(result).toContain('ZZZZ');
    const text = textNode.data;
    const expectedStart = 300 - Math.floor((500 - 4) / 2);
    expect(result).toBe(text.slice(expectedStart, expectedStart + 500));
  });

  it('counts offset correctly across a nested inline element', () => {
    // <p>Hello <strong>AAAA…</strong>BBB…</p>
    const strong = makeElement('STRONG', [makeText('A'.repeat(300))]);
    const p = makeElement('P', [makeText('Hello '), strong, makeText('B'.repeat(200))]);
    installDocument(p);
    const selTextNode = strong.childNodes[0] as MockTextNode;
    // 选中 strong 内前 5 个 "A"，其 offset=0，但在整段 textContent 中偏移为 6（"Hello " 长度）
    const result = extractContextText(makeSelection(p, selTextNode, 0, 'AAAAA'));

    expect(result.length).toBe(500);
    expect(result.startsWith('Hello ')).toBe(true);
    expect(result).toContain('AAAAA');
  });

  it('right-aligns the window when selection sits near the end', () => {
    const p = makeElement('P', [makeText('A'.repeat(540) + 'ZZZZ' + 'B'.repeat(96))]); // length 600
    installDocument(p);
    const textNode = p.childNodes[0] as MockTextNode;
    const text = textNode.data;
    const result = extractContextText(makeSelection(p, textNode, 540, 'ZZZZ'));

    expect(result.length).toBe(500);
    expect(result).toBe(text.slice(text.length - 500));
    expect(result).toContain('ZZZZ');
  });
});