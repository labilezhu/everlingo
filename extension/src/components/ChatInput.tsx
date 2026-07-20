import type { FormEvent, KeyboardEvent } from 'react';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

interface ChatInputProps {
  onSend: (text: string) => void;
  disabled: boolean;
  pending: boolean;
}

export default function ChatInput({ onSend, disabled, pending }: ChatInputProps) {
  function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const data = new FormData(form);
    const text = (data.get('message') as string)?.trim();
    if (!text) return;
    if (pending) return;
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
      <Button type="submit" disabled={disabled} size="lg" className={cn("shrink-0 gap-2 px-4 text-base", pending && "animate-pulse")}>
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14"/><path d="m12 5 7 7-7 7"/></svg>
        发送
      </Button>
    </form>
  );
}
