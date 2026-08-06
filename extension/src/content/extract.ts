const BLOCK_TAGS = new Set([
  'P', 'DIV', 'SECTION', 'ARTICLE', 'LI',
  'H1', 'H2', 'H3', 'H4', 'H5', 'H6',
  'BLOCKQUOTE', 'PRE', 'TD',
]);

const MAX_CONTEXT_LEN = 500;

const TEXT_NODE = 3;
const ELEMENT_NODE = 1;
const SHOW_TEXT = 4;
const DOCUMENT_POSITION_FOLLOWING = 4;

function isBlockElement(el: Element | null): boolean {
  if (!el || !el.tagName) return false;
  return BLOCK_TAGS.has(el.tagName.toUpperCase());
}

// 计算 target 节点在其所属 root 子树 textContent 中的字符偏移。用 TreeWalker 按文档序
// 累加 text 节点长度，避免 selection.toString() 与 textContent 因空白折叠导致索引错位。
function textContentOffset(root: Node, container: Node, offset: number): number {
  const walker = document.createTreeWalker(root, SHOW_TEXT);
  let pos = 0;
  let node: Node | null;
  while ((node = walker.nextNode())) {
    if (node === container) {
      return pos + offset;
    }
    if (container.nodeType === ELEMENT_NODE && container.contains(node)) {
      const child = container.childNodes[offset];
      if (child) {
        if (node.compareDocumentPosition(child) & DOCUMENT_POSITION_FOLLOWING) {
          pos += (node as Text).data.length;
          continue;
        }
        return pos;
      }
    }
    pos += (node as Text).data.length;
  }
  return pos;
}

// 以选词为中心截取 sourceText，保证选词落在返回窗口内。
export function centerWindow(
  sourceText: string,
  selectedText: string,
  selStart: number,
  maxLen: number = MAX_CONTEXT_LEN,
): string {
  if (sourceText.length <= maxLen) return sourceText;
  if (!selectedText) return sourceText.slice(0, maxLen);
  const selLen = Math.min(selectedText.length, maxLen);
  let start = Math.max(0, selStart - Math.floor((maxLen - selLen) / 2));
  let end = start + maxLen;
  if (end > sourceText.length) {
    end = sourceText.length;
    start = Math.max(0, end - maxLen);
  }
  return sourceText.slice(start, end);
}

export function extractContextText(selection: Selection): string {
  if (!selection.rangeCount) return '';
  const range = selection.getRangeAt(0);
  let block: Element | null = range.commonAncestorContainer as Element;
  while (block && !isBlockElement(block)) {
    block = block.parentElement;
  }
  const sourceText = block
    ? block.textContent || ''
    : document.body.textContent || '';
  if (sourceText.length <= MAX_CONTEXT_LEN) return sourceText;
  const selStart = textContentOffset(block ?? document.body, range.startContainer, range.startOffset);
  return centerWindow(sourceText, selection.toString(), selStart);
}

export function extractSelection(): string {
  return window.getSelection()?.toString() || '';
}

export interface PageSnapshot {
  text: string;
  paragraph_text: string;
}

export function captureSnapshot(): PageSnapshot {
  const text = extractSelection();
  let paragraph_text = '';
  if (text) {
    const sel = window.getSelection();
    if (sel) {
      paragraph_text = extractContextText(sel);
    }
  }
  return { text, paragraph_text };
}