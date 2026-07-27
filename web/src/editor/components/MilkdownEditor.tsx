import { useCallback, useEffect, useRef, type MutableRefObject } from 'react';
import { Editor, rootCtx, defaultValueCtx, editorViewCtx } from '@milkdown/kit/core';
import { MilkdownProvider, useEditor, Milkdown } from '@milkdown/react';
import { commonmark } from '@milkdown/kit/preset/commonmark';
import { gfm } from '@milkdown/kit/preset/gfm';
import { history } from '@milkdown/kit/plugin/history';
import { listener, listenerCtx } from '@milkdown/kit/plugin/listener';
import { ghostSelectionPlugin } from './ghostSelectionPlugin';
import SourceEditor from './SourceEditor';

interface MilkdownEditorProps {
  content: string;
  onChange: (value: string) => void;
  mode: 'source' | 'wysiwyg';
  onLinkClick?: (href: string) => boolean;
  selectionRef: MutableRefObject<() => { text: string; start_line: number | null; start_column: number | null; paragraph_text: string | null }>;
}

function WysiwygEditor({ content, onChange, onLinkClick, selectionRef }: {
  content: string;
  onChange: (v: string) => void;
  onLinkClick?: (href: string) => boolean;
  selectionRef: MilkdownEditorProps['selectionRef'];
}) {
  const firstUpdate = useRef(true);

  const { get } = useEditor((container) => {
    return Editor
      .make()
      .config(ctx => {
        ctx.set(rootCtx, container);
        ctx.set(defaultValueCtx, content);
      })
      .use(commonmark)
      .use(gfm)
      .use(history)
      .use(listener)
      .use(ghostSelectionPlugin)
      .config(ctx => {
        const listenerApi = ctx.get(listenerCtx);
        listenerApi.markdownUpdated((_ctx, markdown, _prev) => {
          if (firstUpdate.current) {
            firstUpdate.current = false;
            return;
          }
          onChange(markdown);
        });
      });
  }, []);

  useEffect(() => {
    selectionRef.current = () => {
      try {
        const editor = get();
        if (!editor) return { text: '', start_line: null, start_column: null, paragraph_text: null };
        const view = editor.ctx.get(editorViewCtx);
        const { from, to } = view.state.selection;
        if (from === to) return { text: '', start_line: null, start_column: null, paragraph_text: null };
        const text = view.state.doc.textBetween(from, to, '\n');
        const $from = view.state.selection.$from;
        const parent = $from.node();
        const paragraph_text = parent.textContent.slice(0, 500);
        return { text, start_line: null, start_column: null, paragraph_text };
      } catch {
        return { text: '', start_line: null, start_column: null, paragraph_text: null };
      }
    };
  }, [selectionRef, get]);

  const handleClick = useCallback((e: React.MouseEvent) => {
    const anchor = (e.target as HTMLElement).closest('a[href]');
    if (!anchor) return;
    if (!anchor.closest('[data-milkdown-root]')) return;
    e.preventDefault();
    const href = (anchor as HTMLAnchorElement).getAttribute('href');
    if (!href) return;
    if (onLinkClick && onLinkClick(href)) return;
    window.open(href, '_blank', 'noopener,noreferrer');
  }, [onLinkClick]);

    return (
      <div className="w-full h-full overflow-auto" onClick={handleClick}>
        <style>{`
          .pm-ghost-selection { background-color: oklch(0.9 0.02 260); border-radius: 0.125rem; }
          [data-milkdown-root] {
            min-height: 100%;
            padding: 1rem;
            font-family: 'Geist Variable', sans-serif;
            font-size: 0.875rem;
            line-height: 1.625;
          }
          .ProseMirror,
          .ProseMirror:focus,
          .ProseMirror:focus-visible {
            outline: none;
          }
          [data-milkdown-root] h1 { font-size: 1.5rem; font-weight: 700; margin: 0.5em 0 0.25em; }
          [data-milkdown-root] h2 { font-size: 1.25rem; font-weight: 600; margin: 0.5em 0 0.25em; }
          [data-milkdown-root] h3 { font-size: 1.125rem; font-weight: 600; margin: 0.5em 0 0.25em; }
          [data-milkdown-root] p { margin: 0.5em 0; }
          [data-milkdown-root] ul, [data-milkdown-root] ol { padding-left: 1.5rem; }
          [data-milkdown-root] li { margin: 0.25em 0; }
          [data-milkdown-root] code {
            background: oklch(0.97 0 0);
            border-radius: 0.25rem;
            padding: 0.125rem 0.375rem;
            font-size: 0.8em;
          }
          [data-milkdown-root] pre code {
            display: block;
            padding: 1rem;
            overflow-x: auto;
            background: oklch(0.97 0 0);
            border-radius: 0.375rem;
          }
          [data-milkdown-root] blockquote {
            border-left: 3px solid oklch(0.87 0 0);
            padding-left: 1rem;
            margin: 0.5em 0;
            color: oklch(0.55 0 0);
          }
          [data-milkdown-root] a { color: oklch(0.45 0.2 260); text-decoration: underline; cursor: pointer; }
          [data-milkdown-root] img { max-width: 100%; height: auto; border-radius: 0.375rem; }
          [data-milkdown-root] hr { margin: 1em 0; border-color: oklch(0.92 0 0); }
        `}</style>
        <Milkdown />
      </div>
    );
}

export default function MilkdownEditor({ content, onChange, mode, onLinkClick, selectionRef }: MilkdownEditorProps) {
  if (mode === 'source') {
    return <SourceEditor content={content} onChange={onChange} selectionRef={selectionRef} />;
  }

  return (
    <MilkdownProvider>
      <WysiwygEditor content={content} onChange={onChange} onLinkClick={onLinkClick} selectionRef={selectionRef} />
    </MilkdownProvider>
  );
}
