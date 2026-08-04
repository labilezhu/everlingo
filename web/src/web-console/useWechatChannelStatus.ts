import { useEffect, useState } from 'react';
import { apiFetch } from '@/services/apiFetch';

export type WechatChannelState =
  | 'stopped'
  | 'conflict'
  | 'starting'
  | 'waiting_scan'
  | 'scanned'
  | 'logined';

export interface WechatChannelStatus {
  running: boolean;
  state: WechatChannelState;
  qr_url: string | null;
  last_error: string | null;
}

const STOPPED: WechatChannelStatus = {
  running: false,
  state: 'stopped',
  qr_url: null,
  last_error: null,
};

async function api<T>(url: string, init?: RequestInit): Promise<T> {
  // 401 由 apiFetch 统一兜底跳 /login
  const res = await apiFetch(url, init);
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (body.detail) detail = body.detail;
    } catch { /* fall through */ }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export function fetchWechatStatus(): Promise<WechatChannelStatus> {
  return api<WechatChannelStatus>('/api/wechat-channel/status');
}

export function startWechat(): Promise<WechatChannelStatus> {
  return api<WechatChannelStatus>('/api/wechat-channel/start', { method: 'POST' });
}

export function stopWechat(): Promise<WechatChannelStatus> {
  return api<WechatChannelStatus>('/api/wechat-channel/stop', { method: 'POST' });
}

const POLL_INTERVAL_MS = 2000;

export function useWechatChannelStatus() {
  const [status, setStatus] = useState<WechatChannelStatus>(STOPPED);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function poll() {
      try {
        const s = await fetchWechatStatus();
        if (!cancelled) {
          setStatus(s);
          setError(null);
        }
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : String(e));
        }
      }
    }

    void poll();
    const timer = setInterval(poll, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  return { status, error };
}
