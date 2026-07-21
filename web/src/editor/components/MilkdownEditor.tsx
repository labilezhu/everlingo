import { useRef } from 'react';
import { Editor, rootCtx, defaultValueCtx } from '@milkdown/kit/core';
import { MilkdownProvider, useEditor, Milkdown } from '@milkdown/react';
import { commonmark } from '@milkdown/kit/preset/commonmark';
import { gfm } from '@milkdown/kit/preset/gfm';
import { history } from '@milkdown/kit/plugin/history';
import { listener, listenerCtx } from '@milkdown/kit/plugin/listener';

interface MilkdownEditorProps {
  content: string;
  onChange: (value: string) => void;
  mode: 'source' | 'wysiwyg';
}

function WysiwygEditor({ content, onChange }: { content: string; onChange: (v: string) => void }) {
  const firstUpdate = useRef(true);

  useEditor((container) => {
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

    return (
      <div className="w-full h-full overflow-auto">
        <style>{`
          [data-milkdown-root] {
            min-height: 100%;
            padding: 1rem;
            font-family: 'Geist Variable', sans-serif;
            font-size: 0.875rem;
            line-height: 1.625;
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
          [data-milkdown-root] a { color: oklch(0.45 0.2 260); text-decoration: underline; }
          [data-milkdown-root] img { max-width: 100%; height: auto; border-radius: 0.375rem; }
          [data-milkdown-root] hr { margin: 1em 0; border-color: oklch(0.92 0 0); }
        `}</style>
        <Milkdown />
      </div>
    );
}

export default function MilkdownEditor({ content, onChange, mode }: MilkdownEditorProps) {
  if (mode === 'source') {
    return (
      <textarea
        className="w-full h-full resize-none bg-transparent p-4 font-mono text-sm leading-relaxed outline-none"
        value={content}
        onChange={e => onChange(e.target.value)}
        placeholder="请输入 Markdown 内容…"
      />
    );
  }

  return (
    <MilkdownProvider>
      <WysiwygEditor content={content} onChange={onChange} />
    </MilkdownProvider>
  );
}
