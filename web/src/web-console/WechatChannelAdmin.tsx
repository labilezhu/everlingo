import { useState } from 'react';
import { QrCode, RefreshCw, Square, Play } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { startWechat, stopWechat, useWechatChannelStatus } from './useWechatChannelStatus';

export default function WechatChannelAdmin() {
  const { t } = useTranslation('web-console');
  const { status, error } = useWechatChannelStatus();
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const { running, state, qr_url, last_error } = status;

  const statusText = (s: string): { text: string; dot: string } => {
    switch (s) {
      case 'starting':
        return { text: t('status_starting'), dot: 'bg-amber-500' };
      case 'waiting_scan':
        return { text: t('status_waiting_scan'), dot: 'bg-blue-500' };
      case 'scanned':
        return { text: t('status_scanned'), dot: 'bg-amber-500' };
      case 'logined':
        return { text: t('status_logined'), dot: 'bg-green-500' };
      case 'conflict':
        return { text: t('status_conflict'), dot: 'bg-red-500' };
      default:
        return { text: running ? state : t('not_running'), dot: 'bg-muted-foreground' };
    }
  };

  const { text, dot } = statusText(state);
  const conflict = state === 'conflict';

  async function handleStart() {
    setBusy(true);
    setActionError(null);
    try {
      await startWechat();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleStop() {
    setBusy(true);
    setActionError(null);
    try {
      await stopWechat();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  function openQr() {
    if (qr_url) {
      window.open(qr_url, '_blank', 'noopener');
    }
  }

  return (
    <div className="p-4 space-y-4">
      <div className="rounded-xl border border-border bg-background p-4 space-y-4">
        <div className="flex items-center gap-3">
          <span className={'size-2.5 rounded-full shrink-0 ' + dot} />
          <div className="min-w-0">
            <div className="text-sm font-medium text-foreground">{text}</div>
            <div className="text-xs text-muted-foreground mt-0.5">
              {running ? t('running') : state === 'conflict' ? t('lock_conflict') : t('not_running_short')}
            </div>
          </div>
        </div>

        {last_error && (
          <div className="px-3 py-2 bg-red-50 text-red-600 text-sm rounded-lg border border-red-200">
            {last_error}
          </div>
        )}
        {actionError && (
          <div className="px-3 py-2 bg-red-50 text-red-600 text-sm rounded-lg border border-red-200">
            {actionError}
          </div>
        )}

        <div className="flex flex-wrap gap-2">
          {!running && !conflict && (
            <Button size="sm" onClick={handleStart} disabled={busy}>
              <Play />
              {t('start')}
            </Button>
          )}
          {conflict && (
            <Button size="sm" variant="outline" onClick={handleStart} disabled={busy}>
              <RefreshCw />
              {t('retry')}
            </Button>
          )}
          {state === 'waiting_scan' && qr_url && (
            <Button size="sm" variant="outline" onClick={openQr}>
              <QrCode />
              {t('open_scan_page')}
            </Button>
          )}
          {running && (
            <Button size="sm" variant="destructive" onClick={handleStop} disabled={busy}>
              <Square />
              {t('stop')}
            </Button>
          )}
        </div>
      </div>

      {error && (
        <div className="px-3 py-2 bg-amber-50 text-amber-700 text-sm rounded-lg border border-amber-200">
          {t('poll_failed', { error })}
        </div>
      )}
    </div>
  );
}