import { useRef, useState } from 'react';
import MarkdownRenderer from './MarkdownRenderer';
import type { Message } from '@/types/chat';

export default function MessageBubble({
  message,
  onReplay,
}: {
  message: Message;
  onReplay?: (url: string) => void;
}) {
  const isUser = message.from === 'user';
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState(false);

  if (message.audioUrl) {
    const toggle = () => {
      const url = message.audioUrl!;
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current = null;
        setPlaying(false);
        return;
      }
      const audio = new Audio(url);
      audioRef.current = audio;
      audio.onended = () => { audioRef.current = null; setPlaying(false); };
      audio.onpause = () => setPlaying(false);
      audio.onplay = () => setPlaying(true);
      audio.play().catch(() => { audioRef.current = null; setPlaying(false); });
      onReplay?.(url);
    };

    return (
      <div className="flex justify-start">
        <button
          type="button"
          onClick={toggle}
          className="bg-muted text-foreground rounded-2xl rounded-bl-md px-4 py-2 flex items-center gap-2 hover:bg-muted/80 transition-colors"
          aria-label={playing ? '停止播放' : '播放语音'}
        >
          <span className="text-lg leading-none">{playing ? '⏸' : '▶️'}</span>
          <span className="text-sm">语音消息</span>
        </button>
      </div>
    );
  }

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