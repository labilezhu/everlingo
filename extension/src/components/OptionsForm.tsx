import { useEffect, useState } from 'react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Eye, EyeOff } from 'lucide-react';
import {
  DEFAULT_API_BASE_URL,
  SERVER_URL_STORAGE_KEY,
  SERVER_USERNAME_STORAGE_KEY,
  SERVER_PASSWORD_STORAGE_KEY,
  normalizeUrl,
  buildBasicAuthHeader,
} from '@/config';

export default function OptionsForm() {
  const [url, setUrl] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPwd, setShowPwd] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState('');
  const [testStatus, setTestStatus] = useState<'idle' | 'loading' | 'ok' | 'fail'>('idle');
  const [testMsg, setTestMsg] = useState('');

  useEffect(() => {
    (async () => {
      const items = await chrome.storage.local.get([
        SERVER_URL_STORAGE_KEY,
        SERVER_USERNAME_STORAGE_KEY,
        SERVER_PASSWORD_STORAGE_KEY,
      ]);
      setUrl(typeof items[SERVER_URL_STORAGE_KEY] === 'string' ? items[SERVER_URL_STORAGE_KEY] : DEFAULT_API_BASE_URL);
      setUsername(typeof items[SERVER_USERNAME_STORAGE_KEY] === 'string' ? items[SERVER_USERNAME_STORAGE_KEY] : '');
      setPassword(typeof items[SERVER_PASSWORD_STORAGE_KEY] === 'string' ? items[SERVER_PASSWORD_STORAGE_KEY] : '');
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
        [SERVER_USERNAME_STORAGE_KEY]: username,
        [SERVER_PASSWORD_STORAGE_KEY]: password,
      });
      setUrl(normalized);
      setSaved(true);
      setError('');
    } catch (e) {
      setSaved(false);
      setError(e instanceof Error ? e.message : '保存失败');
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
      setTestMsg(e instanceof Error ? e.message : '服务端地址格式错误');
      return;
    }

    const authHeader = buildBasicAuthHeader(username, password);
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
        setTestMsg(res.ok ? '连接成功' : '连接成功（服务端已就绪）');
      } else if (res.status === 401 || res.status === 403) {
        setTestStatus('fail');
        setTestMsg(res.status === 401 ? '用户名或密码错误（401）' : '访问被拒绝（403），请检查凭据');
      } else {
        setTestStatus('fail');
        setTestMsg(`服务端返回异常状态码 ${res.status}`);
      }
    } catch (e) {
      clearTimeout(timer);
      controller.abort();
      setTestStatus('fail');
      if (e instanceof DOMException && e.name === 'AbortError') {
        setTestMsg('连接超时（3 秒），请检查地址是否正确');
      } else {
        setTestMsg('无法连接，请检查服务端地址和网络');
      }
    }
  }

  return (
    <div className="min-h-screen bg-background p-6">
      <div className="max-w-md mx-auto space-y-5">
        <header className="flex items-center gap-2">
          <span className="text-2xl">🐹</span>
          <h1 className="text-xl font-semibold text-foreground">小记 设置</h1>
        </header>

        <div className="space-y-2">
          <label className="text-sm font-medium text-foreground" htmlFor="server-url">服务端地址</label>
          <Input
            id="server-url"
            value={url}
            onChange={(e) => { setUrl(e.target.value); markUnsaved(); }}
            placeholder={DEFAULT_API_BASE_URL}
          />
          <p className="text-xs text-muted-foreground">
            默认 {DEFAULT_API_BASE_URL}。修改后请刷新或重开 sidecar 面板生效。
          </p>
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium text-foreground" htmlFor="server-username">服务端用户名</label>
          <Input
            id="server-username"
            value={username}
            onChange={(e) => { setUsername(e.target.value); markUnsaved(); }}
            placeholder="（若 Nginx 启用了 Basic Auth 则填写）"
            autoComplete="username"
          />
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium text-foreground" htmlFor="server-password">服务端密码</label>
          <div className="relative">
            <Input
              id="server-password"
              type={showPwd ? 'text' : 'password'}
              value={password}
              onChange={(e) => { setPassword(e.target.value); markUnsaved(); }}
              placeholder="（留空则不启用 Basic Auth）"
              autoComplete="current-password"
              className="pr-10"
            />
            <button
              type="button"
              onClick={() => setShowPwd((v) => !v)}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              tabIndex={-1}
              aria-label={showPwd ? '隐藏密码' : '显示密码'}
            >
              {showPwd ? <EyeOff size={18} /> : <Eye size={18} />}
            </button>
          </div>
        </div>

        <div className="flex gap-2">
          <Button onClick={handleSave}>保存</Button>
          <Button variant="outline" onClick={handleTest} disabled={testStatus === 'loading'}>
            {testStatus === 'loading' ? '测试中…' : '测试连接'}
          </Button>
        </div>

        {saved && <p className="text-sm text-green-600">已保存</p>}
        {error && <p className="text-sm text-red-600">{error}</p>}

        {testStatus === 'ok' && <p className="text-sm text-green-600">{testMsg}</p>}
        {testStatus === 'fail' && <p className="text-sm text-red-600">{testMsg}</p>}
      </div>
    </div>
  );
}
