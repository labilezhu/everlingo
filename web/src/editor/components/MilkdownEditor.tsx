interface MilkdownEditorProps {
  content: string;
  onChange: (value: string) => void;
}

export default function MilkdownEditor({ content, onChange }: MilkdownEditorProps) {
  return (
    <textarea
      className="w-full h-full resize-none bg-transparent p-4 font-mono text-sm leading-relaxed outline-none"
      value={content}
      onChange={e => onChange(e.target.value)}
      placeholder="请输入 Markdown 内容…"
    />
  );
}
