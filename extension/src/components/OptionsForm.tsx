import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Eye, EyeOff } from 'lucide-react';
import {
  DEFAULT_API_BASE_URL,
  SERVER_URL_STORAGE_KEY,
  SERVER_TOKEN_STORAGE_KEY,
  normalizeUrl,
  buildBearerHeader,
  UrlFormatError,
} from '@/config';

export default function OptionsForm() {
  const { t } = useTranslation('options');

  function errorText(e: unknown, fallback: string): string {
    if (e instanceof UrlFormatError) return t('url_format_error');
    return e instanceof Error ? e.message : fallback;
  }
  const [url, setUrl] = useState('');
  const [token, setToken] = useState('');
  const [showToken, setShowToken] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState('');
  const [testStatus, setTestStatus] = useState<'idle' | 'loading' | 'ok' | 'fail'>('idle');
  const [testMsg, setTestMsg] = useState('');

  useEffect(() => {
    (async () => {
      const items = await chrome.storage.local.get([
        SERVER_URL_STORAGE_KEY,
        SERVER_TOKEN_STORAGE_KEY,
      ]);
      setUrl(typeof items[SERVER_URL_STORAGE_KEY] === 'string' ? items[SERVER_URL_STORAGE_KEY] : DEFAULT_API_BASE_URL);
      setToken(typeof items[SERVER_TOKEN_STORAGE_KEY] === 'string' ? items[SERVER_TOKEN_STORAGE_KEY] : '');
    })();
  }, []);

  function markUnsaved() {
    setSaved(false);
    setError('');
    setTestStatus('idle');
    setTestMsg('');
  }

  async function handleSave() {
    try {
      const normalized = normalizeUrl(url);
      await chrome.storage.local.set({
        [SERVER_URL_STORAGE_KEY]: normalized,
        [SERVER_TOKEN_STORAGE_KEY]: token,
      });
      setUrl(normalized);
      setSaved(true);
      setError('');
    } catch (e) {
      setSaved(false);
      setError(errorText(e, t('save_failed')));
    }
  }

  async function handleTest() {
    setTestStatus('loading');
    setTestMsg('');

    let base: string;
    try {
      base = normalizeUrl(url);
    } catch (e) {
      setTestStatus('fail');
      setTestMsg(errorText(e, t('url_format_error')));
      return;
    }

    const authHeader = buildBearerHeader(token);
    const headers: Record<string, string> = { Accept: 'text/event-stream' };
    if (authHeader) {
      headers['Authorization'] = authHeader;
    }

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 3000);

    try {
      const res = await fetch(`${base}/api/session/__probe__/events`, { headers, signal: controller.signal });
      clearTimeout(timer);
      controller.abort();

      if (res.ok || res.status === 404) {
        setTestStatus('ok');
        setTestMsg(res.ok ? t('connect_ok') : t('connect_ok_ready'));
      } else if (res.status === 401 || res.status === 403) {
        setTestStatus('fail');
        setTestMsg(res.status === 401 ? t('token_invalid') : t('access_denied'));
      } else {
        setTestStatus('fail');
        setTestMsg(t('bad_status', { status: res.status }));
      }
    } catch (e) {
      clearTimeout(timer);
      controller.abort();
      setTestStatus('fail');
      if (e instanceof DOMException && e.name === 'AbortError') {
        setTestMsg(t('timeout'));
      } else {
        setTestMsg(t('cannot_connect'));
      }
    }
  }

  return (
    <div className="min-h-screen bg-background p-6">
      <div className="max-w-md mx-auto space-y-5">
        <header className="flex items-center gap-2">
          <span className="text-2xl">🐹</span>
          <h1 className="text-xl font-semibold text-foreground">{t('title')}</h1>
        </header>

        <div className="space-y-2">
          <label className="text-sm font-medium text-foreground" htmlFor="server-url">{t('server_url')}</label>
          <Input
            id="server-url"
            value={url}
            onChange={(e) => { setUrl(e.target.value); markUnsaved(); }}
            placeholder={DEFAULT_API_BASE_URL}
          />
          <p className="text-xs text-muted-foreground">
            {t('server_url_hint', { url: DEFAULT_API_BASE_URL })}
          </p>
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium text-foreground" htmlFor="server-token">{t('server_token')}</label>
          <div className="relative">
            <Input
              id="server-token"
              type={showToken ? 'text' : 'password'}
              value={token}
              onChange={(e) => { setToken(e.target.value); markUnsaved(); }}
              placeholder={t('token_placeholder')}
              autoComplete="off"
              className="pr-10"
            />
            <button
              type="button"
              onClick={() => setShowToken((v) => !v)}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              tabIndex={-1}
              aria-label={showToken ? t('hide_token') : t('show_token')}
            >
              {showToken ? <EyeOff size={18} /> : <Eye size={18} />}
            </button>
          </div>
          <p className="text-xs text-muted-foreground">
            {t('token_hint_before')}{' '}
            <code className="text-xs bg-muted px-1 rounded">everlingo ws_master pat add --user &lt;name&gt; --label &lt;label&gt;</code>{' '}
            {t('token_hint_after')}
          </p>
        </div>

        <div className="flex gap-2">
          <Button onClick={handleSave}>{t('save')}</Button>
          <Button variant="outline" onClick={handleTest} disabled={testStatus === 'loading'}>
            {testStatus === 'loading' ? t('testing') : t('test_connection')}
          </Button>
        </div>

        {saved && <p className="text-sm text-green-600">{t('saved')}</p>}
        {error && <p className="text-sm text-red-600">{error}</p>}

        {testStatus === 'ok' && <p className="text-sm text-green-600">{testMsg}</p>}
        {testStatus === 'fail' && <p className="text-sm text-red-600">{testMsg}</p>}
      </div>
    </div>
  );
}
