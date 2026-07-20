const BLOCK_TAGS = new Set([
  'P', 'DIV', 'SECTION', 'ARTICLE', 'LI',
  'H1', 'H2', 'H3', 'H4', 'H5', 'H6',
  'BLOCKQUOTE', 'PRE', 'TD',
]);

function isBlockElement(el: Element | null): boolean {
  if (!el || !el.tagName) return false;
  return BLOCK_TAGS.has(el.tagName.toUpperCase());
}

export function extractContextText(selection: Selection): string {
  if (!selection.rangeCount) return '';
  const range = selection.getRangeAt(0);
  let block: Element | null = range.commonAncestorContainer as Element;
  while (block && !isBlockElement(block)) {
    block = block.parentElement;
  }
  if (block) {
    const text = block.textContent || '';
    return text.length > 500 ? text.slice(0, 500) : text;
  }
  const fullText = document.body.innerText;
  const start = Math.max(0, range.startOffset - 250);
  return fullText.slice(start, start + 500);
}

export function extractSelection(): string {
  return window.getSelection()?.toString() || '';
}

export function extractPageInfo(): { url: string; title: string } {
  return { url: location.href, title: document.title };
}

export interface PageSnapshot {
  selection: string;
  context: string;
  url: string;
  title: string;
}

export function captureSnapshot(): PageSnapshot {
  const selection = extractSelection();
  let context = '';
  if (selection) {
    const sel = window.getSelection();
    if (sel) {
      context = extractContextText(sel);
    }
  }
  const { url, title } = extractPageInfo();
  return { selection, context, url, title };
}
