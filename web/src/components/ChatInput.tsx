import type { FormEvent, KeyboardEvent } from 'react';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';

interface ChatInputProps {
  onSend: (text: string) => void;
  disabled: boolean;
}

export default function ChatInput({ onSend, disabled }: ChatInputProps) {
  function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const data = new FormData(form);
    const text = (data.get('message') as string)?.trim();
    if (!text) return;
    onSend(text);
    form.reset();
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      e.currentTarget.form?.requestSubmit();
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex items-end gap-2 border-t border-border px-4 py-3">
      <Textarea
        name="message"
        placeholder="输入单词、句子或提问..."
        onKeyDown={handleKeyDown}
        disabled={disabled}
        className="min-h-10 resize-none"
        rows={1}
      />
      <Button type="submit" disabled={disabled} className="shrink-0">
        发送
      </Button>
    </form>
  );
}
