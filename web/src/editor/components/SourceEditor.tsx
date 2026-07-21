import { useEffect, useRef } from 'react';
import { EditorState } from '@codemirror/state';
import { EditorView, keymap } from '@codemirror/view';
import { defaultKeymap, historyKeymap, history, indentWithTab } from '@codemirror/commands';
import { markdown } from '@codemirror/lang-markdown';
import { languages } from '@codemirror/language-data';
import { syntaxHighlighting, HighlightStyle, Language } from '@codemirror/language';
import { tags } from '@lezer/highlight';

const langMap = new Map<string, Language>();

const preloadTargets = ['yaml', 'json', 'bash', 'sh', 'markdown', 'python', 'go', 'sql', 'typescript', 'javascript', 'jsx', 'tsx', 'html', 'css'];
for (const fence of preloadTargets) {
  const desc = languages.find(l =>
    l.name.toLowerCase() === fence ||
    l.alias.some(a => a.toLowerCase() === fence)
  );
  if (desc) {
    desc.load().then(support => {
      for (const a of [desc.name, ...desc.alias]) {
        langMap.set(a.toLowerCase(), support.language);
      }
    });
  }
}

const customHighlightStyle = HighlightStyle.define([
  { tag: tags.heading, fontWeight: '700', color: 'oklch(0.20 0 0)' },
  { tag: tags.heading1, fontSize: '1.5rem' },
  { tag: tags.heading2, fontSize: '1.25rem' },
  { tag: tags.heading3, fontSize: '1.125rem' },
  { tag: tags.strong, fontWeight: '700' },
  { tag: tags.emphasis, fontStyle: 'italic' },
  { tag: tags.monospace, background: 'oklch(0.97 0 0)', borderRadius: '0.25rem', padding: '0.125rem 0.375rem' },
  { tag: tags.link, color: 'oklch(0.45 0.2 260)', textDecoration: 'underline' },
  { tag: tags.url, color: 'oklch(0.45 0.2 260)', textDecoration: 'underline' },
  { tag: tags.quote, color: 'oklch(0.55 0 0)' },
  { tag: tags.list, color: 'oklch(0.55 0 0)' },
  { tag: tags.separator, color: 'oklch(0.6 0 0)' },
  { tag: tags.strikethrough, textDecoration: 'line-through' },
  { tag: tags.keyword, color: '#8250df' },
  { tag: tags.string, color: '#0a3069' },
  { tag: tags.number, color: '#0550ae' },
  { tag: tags.bool, color: '#8250df' },
  { tag: tags.comment, color: '#6e7781', fontStyle: 'italic' },
  { tag: tags.typeName, color: '#116329' },
  { tag: tags.propertyName, color: '#0550ae' },
  { tag: tags.atom, color: '#0550ae' },
  { tag: tags.operator, color: '#0550ae' },
  { tag: tags.punctuation, color: '#57606a' },
  { tag: tags.labelName, color: '#116329' },
  { tag: tags.tagName, color: '#116329' },
  { tag: tags.attributeName, color: '#0550ae' },
  { tag: tags.attributeValue, color: '#0a3069' },
  { tag: tags.bracket, color: '#57606a' },
  { tag: tags.meta, color: '#57606a' },
  { tag: tags.content, color: 'oklch(0.20 0 0)' },
  { tag: tags.docComment, color: '#6e7781', fontStyle: 'italic' },
]);

const editorTheme = EditorView.theme({
  '&': {
    backgroundColor: 'transparent',
    height: '100%',
    fontSize: '0.875rem',
  },
  '&.cm-editor': {
    outline: 'none',
  },
  '&.cm-editor.cm-focused': {
    outline: 'none',
  },
  '.cm-scroller': {
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace",
    lineHeight: '1.625',
  },
  '.cm-content': {
    caretColor: 'oklch(0.20 0 0)',
    padding: '1rem',
  },
  '.cm-line': {
    padding: '0',
  },
  '.cm-selectionBackground': {
    backgroundColor: 'oklch(0.9 0.02 260)',
  },
  '&.cm-focused .cm-selectionBackground': {
    backgroundColor: 'oklch(0.85 0.04 260)',
  },
  '.cm-cursor': {
    borderLeftColor: 'oklch(0.20 0 0)',
  },
  '.cm-activeLine': {
    backgroundColor: 'transparent',
  },
  '.cm-gutters': {
    display: 'none',
  },
});

interface SourceEditorProps {
  content: string;
  onChange: (value: string) => void;
}

export default function SourceEditor({ content, onChange }: SourceEditorProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const view = new EditorView({
      state: EditorState.create({
        doc: content,
        extensions: [
          EditorView.lineWrapping,
          history(),
          keymap.of([...defaultKeymap, ...historyKeymap, indentWithTab]),
          markdown({
            codeLanguages: (name: string) => langMap.get(name.toLowerCase()) ?? null,
          }),
          syntaxHighlighting(customHighlightStyle, { fallback: true }),
          editorTheme,
          EditorView.updateListener.of(update => {
            if (update.docChanged) {
              onChange(update.state.doc.toString());
            }
          }),
        ],
      }),
      parent: containerRef.current,
    });

    return () => {
      view.destroy();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return <div ref={containerRef} className="w-full h-full overflow-auto" />;
}
