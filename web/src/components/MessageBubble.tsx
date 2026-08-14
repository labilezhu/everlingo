import { useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import MarkdownRenderer from './MarkdownRenderer';
import type { Message } from '@/types/chat';

export default function MessageBubble({
  message,
  onReplay,
}: {
  message: Message;
  onReplay?: (url: string) => void;
}) {
  const { t } = useTranslation('chatbot');
  const isUser = message.from === 'user';
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState(false);

  if (message.from === 'system') {
    return (
      <div className="flex justify-center">
        <span className="text-xs text-muted-foreground">{message.text}</span>
      </div>
    );
  }

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
          aria-label={playing ? t('stop_playing') : t('play_voice')}
        >
          <span className="text-lg leading-none">{playing ? '⏸' : '▶️'}</span>
          <span className="text-sm">{t('voice_message')}</span>
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
        {message.imageUrl && (
          <img src={message.imageUrl} alt="" className="mb-2 max-h-48 w-auto rounded-lg object-contain" />
        )}
        {message.text && <MarkdownRenderer content={message.text} />}
      </div>
    </div>
  );
}