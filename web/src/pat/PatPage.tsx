import { useEffect, useState, type FormEvent } from 'react';
import { ArrowLeft, Copy, KeyRound, Plus, Check } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { apiFetch } from '@/services/apiFetch';

interface Pat {
  id: string;
  label: string;
  created_at: string;
  last_used_at: string | null;
  expires_at: string | null;
}

export default function PatPage() {
  const [pats, setPats] = useState<Pat[]>([]);
  const [label, setLabel] = useState('');
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [newToken, setNewToken] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  async function loadPats() {
    try {
      const resp = await apiFetch('/self-service/api/pats', {
        headers: { 'Accept': 'application/json' },
      });
      if (resp.ok) {
        setPats(await resp.json());
      } else {
        setError('加载 Token 列表失败');
      }
    } catch {
      setError('加载 Token 列表失败');
    }
  }

  useEffect(() => { loadPats(); }, []);

  function goBack() {
    if (window.history.length > 1) {
      window.history.back();
    } else {
      window.location.href = '/self-service';
    }
  }

  async function handleCreate(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setCopied(false);
    setCreating(true);
    try {
      const resp = await apiFetch('/self-service/api/pats', {
        method: 'POST',
        headers: { 'Accept': 'application/json', 'Content-Type': 'application/json' },
        body: JSON.stringify({ label }),
      });
      if (resp.ok) {
        const data = await resp.json();
        setNewToken(data.token);
        setLabel('');
        await loadPats();
      } else {
        const data = await resp.json().catch(() => null);
        setError(data?.error?.message ?? '生成 Token 失败');
      }
    } catch {
      setError('网络错误，请重试');
    } finally {
      setCreating(false);
    }
  }

  async function copyToken() {
    if (!newToken) return;
    await navigator.clipboard.writeText(newToken);
    setCopied(true);
  }

  return (
    <div className="flex flex-col h-screen mx-auto max-w-md border-x border-border">
      <header className="flex items-center gap-2 px-3 py-2 md:px-4 md:py-3 border-b border-border bg-background shrink-0">
        <Button variant="ghost" size="sm" onClick={goBack}>
          <ArrowLeft />
          <span className="hidden md:inline">返回</span>
        </Button>
        <h1 className="text-lg font-semibold text-foreground">永久 Token</h1>
      </header>

      <main className="flex-1 overflow-y-auto px-3 py-4 md:px-4 space-y-4">
        {error && (
          <p className="rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>
        )}

        {newToken && (
          <div className="rounded-xl border border-border bg-background p-4">
            <p className="text-sm font-medium text-foreground">Token 生成成功</p>
            <p className="mt-1 text-xs text-destructive">仅显示一次，请立即复制保存，关闭后将无法再次查看。</p>
            <div className="mt-3 flex items-center gap-2">
              <code className="min-w-0 flex-1 truncate rounded-lg border border-border bg-muted px-3 py-2 text-xs text-foreground">
                {newToken}
              </code>
              <Button variant="outline" size="sm" onClick={copyToken}>
                {copied ? <Check /> : <Copy />}
                {copied ? '已复制' : '复制'}
              </Button>
            </div>
          </div>
        )}

        <form onSubmit={handleCreate} className="rounded-xl border border-border bg-background p-4">
          <p className="text-sm font-medium text-foreground">生成新 Token</p>
          <div className="mt-3 flex items-center gap-2">
            <Input
              value={label}
              onChange={e => setLabel(e.target.value)}
              placeholder="标签（如 chrome_ext）"
              required
            />
            <Button type="submit" size="sm" disabled={creating}>
              <Plus />
              {creating ? '生成中…' : '生成'}
            </Button>
          </div>
        </form>

        <div>
          <p className="mb-2 flex items-center gap-1.5 text-sm font-medium text-foreground">
            <KeyRound className="size-4 text-muted-foreground" />
            已有 Token
          </p>
          {pats.length === 0 ? (
            <p className="text-sm text-muted-foreground">暂无 Token</p>
          ) : (
            <ul className="space-y-2">
              {pats.map(p => (
                <li
                  key={p.id}
                  className="flex items-center justify-between gap-2 rounded-xl border border-border bg-background px-4 py-3"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-foreground">{p.label}</p>
                    <p className="text-xs text-muted-foreground">
                      创建于 {p.created_at}
                      {p.last_used_at ? ` · 最近使用 ${p.last_used_at}` : ' · 从未使用'}
                    </p>
                  </div>
                  {p.expires_at && (
                    <span className="shrink-0 text-xs text-muted-foreground">{p.expires_at} 过期</span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      </main>
    </div>
  );
}
