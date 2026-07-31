import { useState } from 'react';
import { QrCode, RefreshCw, Square, Play } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { startWechat, stopWechat, useWechatChannelStatus } from './useWechatChannelStatus';

function statusText(state: string, running: boolean): { text: string; dot: string } {
  switch (state) {
    case 'starting':
      return { text: '启动中…', dot: 'bg-amber-500' };
    case 'waiting_scan':
      return { text: '等待扫码', dot: 'bg-blue-500' };
    case 'scanned':
      return { text: '已在手机确认，等待登录完成', dot: 'bg-amber-500' };
    case 'logined':
      return { text: '已登录 ✅', dot: 'bg-green-500' };
    case 'conflict':
      return { text: 'Wechat 已在 standalone 运行，请先停止该进程', dot: 'bg-red-500' };
    default:
      return { text: running ? state : 'Wechat channel 未运行', dot: 'bg-muted-foreground' };
  }
}

export default function WechatChannelAdmin() {
  const { status, error } = useWechatChannelStatus();
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const { running, state, qr_url, last_error } = status;
  const { text, dot } = statusText(state, running);
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
              {running ? '运行中' : state === 'conflict' ? '锁冲突' : '未运行'}
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
              启动
            </Button>
          )}
          {conflict && (
            <Button size="sm" variant="outline" onClick={handleStart} disabled={busy}>
              <RefreshCw />
              重试
            </Button>
          )}
          {state === 'waiting_scan' && qr_url && (
            <Button size="sm" variant="outline" onClick={openQr}>
              <QrCode />
              打开扫码页
            </Button>
          )}
          {running && (
            <Button size="sm" variant="destructive" onClick={handleStop} disabled={busy}>
              <Square />
              停止
            </Button>
          )}
        </div>
      </div>

      {error && (
        <div className="px-3 py-2 bg-amber-50 text-amber-700 text-sm rounded-lg border border-amber-200">
          状态轮询失败：{error}
        </div>
      )}
    </div>
  );
}
