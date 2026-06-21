import MarkdownRenderer from './MarkdownRenderer';
import type { Message } from '@/types/chat';

export default function MessageBubble({ message }: { message: Message }) {
  const isUser = message.from === 'user';

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[80%] rounded-2xl px-4 py-2 ${
          isUser
            ? 'bg-primary text-primary-foreground rounded-br-md'
            : 'bg-muted text-foreground rounded-bl-md'
        }`}
      >
        <MarkdownRenderer content={message.text} />
      </div>
    </div>
  );
}
