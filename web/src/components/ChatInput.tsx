import type { ChangeEvent, ClipboardEvent, FormEvent, KeyboardEvent } from 'react';
import { useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ImagePlus, X } from 'lucide-react';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { uploadImage } from '@/services/sseClient';
import { sha256Hex } from '@/lib/sha256';
import type { MessageAttachment } from '@/types/chat';

interface PendingImage {
  file: File;
  imageUrl: string;
  srcSha256: string;
}

export function computeSha256(buffer: ArrayBuffer): Promise<string> {
  // ref: web-chatbot.md §图片上传 — 客户端计算 src_resource_sha256。
  // 优先用原生 crypto.subtle（仅 HTTPS / localhost 安全上下文可用），
  // 非安全上下文（如局域网 plain HTTP）下回退到纯 JS SHA-256 实现，避免崩溃。
  return sha256Hex(buffer);
}

interface ChatInputProps {
  onSend: (text: string, attachments: MessageAttachment[], imageUrl?: string) => void;
  disabled: boolean;
  pending: boolean;
  sessionId: string | null;
}

export default function ChatInput({ onSend, disabled, pending, sessionId }: ChatInputProps) {
  const { t } = useTranslation('chatbot');
  const [image, setImage] = useState<PendingImage | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function selectFile(file: File | undefined) {
    if (!file) return;
    if (!file.type.startsWith('image/')) return;
    const srcSha256 = await computeSha256(await file.arrayBuffer());
    setImage({ file, imageUrl: URL.createObjectURL(file), srcSha256 });
    setUploadError(null);
  }

  function handleFileChange(e: ChangeEvent<HTMLInputElement>) {
    void selectFile(e.target.files?.[0]);
    e.target.value = '';
  }

  function handlePaste(e: ClipboardEvent<HTMLTextAreaElement>) {
    const items = e.clipboardData?.items;
    if (!items) return;
    for (const item of items) {
      if (item.kind === 'file' && item.type.startsWith('image/')) {
        const file = item.getAsFile();
        if (file) {
          e.preventDefault();
          void selectFile(file);
          return;
        }
      }
    }
  }

  function removeImage() {
    if (image) URL.revokeObjectURL(image.imageUrl);
    setImage(null);
    setUploadError(null);
  }

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const data = new FormData(form);
    const text = (data.get('message') as string)?.trim() ?? '';
    if ((!text && !image) || pending || uploading) return;
    if (pending) return;

    let attachments: MessageAttachment[] = [];
    if (image) {
      setUploading(true);
      setUploadError(null);
      try {
        if (!sessionId) throw new Error('no session');
        await uploadImage(sessionId, image.srcSha256, image.file, image.file.type);
        attachments = [{ src_resource_sha256: image.srcSha256, type: 'image' }];
      } catch (err) {
        setUploading(false);
        setUploadError(t('upload_failed'));
        return;
      }
    }

    onSend(text, attachments, image?.imageUrl);
    removeImage();
    form.reset();
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      e.currentTarget.form?.requestSubmit();
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-2 border-t border-border px-3 pt-2 pb-[calc(0.5rem+env(safe-area-inset-bottom))] md:px-4 md:py-3">
      {image && (
        <div className="flex items-center gap-2">
          <div className="relative">
            <img src={image.imageUrl} alt="" className="h-16 w-16 rounded-md object-cover border border-border" />
            <button type="button" onClick={removeImage} aria-label={t('remove_image')}
              className="absolute -top-2 -right-2 rounded-full bg-foreground text-background p-0.5">
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
          {uploading && <span className="text-xs text-muted-foreground">{t('uploading')}</span>}
        </div>
      )}
      {uploadError && <div className="text-xs text-red-600">{uploadError}</div>}
      <div className="flex items-end gap-2">
        <Button type="button" variant="ghost" size="icon" onClick={() => fileInputRef.current?.click()}
          aria-label={t('attach_image')} className="shrink-0">
          <ImagePlus className="h-5 w-5" />
        </Button>
        <input ref={fileInputRef} type="file" accept="image/jpeg,image/png,image/webp" className="hidden"
          onChange={handleFileChange} />
        <Textarea
          name="message"
          placeholder={t('input_placeholder')}
          onKeyDown={handleKeyDown}
          onPaste={handlePaste}
          disabled={disabled || uploading}
          className="min-h-10 resize-none"
          rows={1}
        />
        <Button type="submit" disabled={disabled || uploading} size="lg" aria-label={t('send')}
          className={cn("shrink-0 gap-2 w-9 md:w-auto px-2.5 md:px-4 text-base", pending && "animate-pulse")}>
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14"/><path d="m12 5 7 7-7 7"/></svg>
          <span className="hidden md:inline">{t('send')}</span>
        </Button>
      </div>
    </form>
  );
}