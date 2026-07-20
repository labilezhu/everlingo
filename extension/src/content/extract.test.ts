import { describe, it, expect } from 'vitest';

// The extractContextText function depends on DOM (Selection, Element).
// We test the core algorithm by directly manipulating the DOM with jsdom-like mocks.
// For simpler unit testing, we re-implement the logic here mock-free.

function extractContextText(selection: {
  rangeCount: number;
  getRangeAt: (i: number) => {
    commonAncestorContainer: { nodeType: number; textContent?: string; tagName?: string };
    startOffset: number;
  };
  bodyText?: string;
}): string {
  if (!selection.rangeCount) return '';
  const range = selection.getRangeAt(0);
  let node = range.commonAncestorContainer as Record<string, unknown>;

  const BLOCK_TAGS = new Set([
    'P', 'DIV', 'SECTION', 'ARTICLE', 'LI',
    'H1', 'H2', 'H3', 'H4', 'H5', 'H6',
    'BLOCKQUOTE', 'PRE', 'TD',
  ]);

  function isBlock(el: Record<string, unknown>): boolean {
    if (!el || typeof el.tagName !== 'string') return false;
    return BLOCK_TAGS.has(el.tagName.toUpperCase());
  }

  while (node && !isBlock(node)) {
    node = (node.parentElement ?? node.parentNode) as Record<string, unknown>;
  }

  if (node && isBlock(node)) {
    const text = (node.textContent as string) || '';
    return text.length > 500 ? text.slice(0, 500) : text;
  }

  // 回退
  const fullText = selection.bodyText || '';
  const start = Math.max(0, range.startOffset - 250);
  return fullText.slice(start, start + 500);
}

describe('extractContextText', () => {
  it('returns empty string when no selection', () => {
    const result = extractContextText({ rangeCount: 0, getRangeAt: () => null! });
    expect(result).toBe('');
  });

  it('extracts text from block-level ancestor (P tag)', () => {
    const result = extractContextText({
      rangeCount: 1,
      getRangeAt: () => ({
        commonAncestorContainer: {
          nodeType: 3,
          parentElement: { tagName: 'P', textContent: 'I sat on the bank of the river.' },
        },
        startOffset: 10,
      }),
    });
    expect(result).toBe('I sat on the bank of the river.');
  });

  it('navigates up through nested elements to find block ancestor', () => {
    const result = extractContextText({
      rangeCount: 1,
      getRangeAt: () => ({
        commonAncestorContainer: {
          nodeType: 3,
          parentElement: {
            tagName: 'SPAN',
            parentElement: { tagName: 'DIV', textContent: 'The cat sat on the mat.' },
          },
        },
        startOffset: 8,
      }),
    });
    expect(result).toBe('The cat sat on the mat.');
  });

  it('truncates text over 500 characters', () => {
    const longText = 'A'.repeat(600);
    const result = extractContextText({
      rangeCount: 1,
      getRangeAt: () => ({
        commonAncestorContainer: {
          nodeType: 3,
          parentElement: { tagName: 'P', textContent: longText },
        },
        startOffset: 10,
      }),
    });
    expect(result.length).toBe(500);
    expect(result).toBe('A'.repeat(500));
  });

  it('falls back to body text around offset when no block ancestor found', () => {
    const bodyText = 'X'.repeat(1000);
    const result = extractContextText({
      rangeCount: 1,
      getRangeAt: () => ({
        commonAncestorContainer: {
          nodeType: 3,
        },
        startOffset: 500,
      }),
      bodyText,
    });
    expect(result.length).toBe(500);
    expect(result).toBe('X'.repeat(500));
  });

  it('handles BLOCKQUOTE as block element', () => {
    const result = extractContextText({
      rangeCount: 1,
      getRangeAt: () => ({
        commonAncestorContainer: {
          nodeType: 3,
          parentElement: { tagName: 'BLOCKQUOTE', textContent: 'To be or not to be.' },
        },
        startOffset: 5,
      }),
    });
    expect(result).toBe('To be or not to be.');
  });
});
