import { useEffect, useState } from 'react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { DEFAULT_API_BASE_URL, SERVER_URL_STORAGE_KEY, normalizeUrl } from '@/config';

export default function OptionsForm() {
  const [value, setValue] = useState('');
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    (async () => {
      const { [SERVER_URL_STORAGE_KEY]: stored } = await chrome.storage.local.get(SERVER_URL_STORAGE_KEY);
      setValue(typeof stored === 'string' ? stored : DEFAULT_API_BASE_URL);
    })();
  }, []);

  async function handleSave() {
    try {
      const normalized = normalizeUrl(value);
      await chrome.storage.local.set({ [SERVER_URL_STORAGE_KEY]: normalized });
      setValue(normalized);
      setSaved(true);
      setError('');
    } catch (e) {
      setSaved(false);
      setError(e instanceof Error ? e.message : '保存失败');
    }
  }

  return (
    <div className="min-h-screen bg-background p-6">
      <div className="max-w-md mx-auto space-y-4">
        <header className="flex items-center gap-2">
          <span className="text-2xl">🐹</span>
          <h1 className="text-xl font-semibold text-foreground">小记 设置</h1>
        </header>

        <div className="space-y-2">
          <label className="text-sm font-medium text-foreground" htmlFor="server-url">服务端地址</label>
          <Input
            id="server-url"
            value={value}
            onChange={(e) => { setValue(e.target.value); setSaved(false); }}
            placeholder={DEFAULT_API_BASE_URL}
          />
          <p className="text-xs text-muted-foreground">
            默认 {DEFAULT_API_BASE_URL}。修改后请刷新或重开 sidecar 面板生效。
          </p>
        </div>

        <Button onClick={handleSave}>保存</Button>

        {saved && <p className="text-sm text-green-600">已保存</p>}
        {error && <p className="text-sm text-red-600">{error}</p>}
      </div>
    </div>
  );
}
