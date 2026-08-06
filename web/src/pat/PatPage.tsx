import { useEffect, useState, type FormEvent } from 'react';
import { ArrowLeft, Copy, KeyRound, Plus, Check } from 'lucide-react';
import { useTranslation } from 'react-i18next';
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
  const { t } = useTranslation('pat');
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
        setError(t('load_failed'));
      }
    } catch {
      setError(t('load_failed'));
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
        setError(data?.error?.message ?? t('created_failed'));
      }
    } catch {
      setError(t('network_error'));
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
          <span className="hidden md:inline">{t('back')}</span>
        </Button>
        <h1 className="text-lg font-semibold text-foreground">{t('title')}</h1>
      </header>

      <main className="flex-1 overflow-y-auto px-3 py-4 md:px-4 space-y-4">
        {error && (
          <p className="rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>
        )}

        {newToken && (
          <div className="rounded-xl border border-border bg-background p-4">
            <p className="text-sm font-medium text-foreground">{t('generated')}</p>
            <p className="mt-1 text-xs text-destructive">{t('show_once')}</p>
            <div className="mt-3 flex items-center gap-2">
              <code className="min-w-0 flex-1 truncate rounded-lg border border-border bg-muted px-3 py-2 text-xs text-foreground">
                {newToken}
              </code>
              <Button variant="outline" size="sm" onClick={copyToken}>
                {copied ? <Check /> : <Copy />}
                {copied ? t('copied') : t('copy')}
              </Button>
            </div>
          </div>
        )}

        <form onSubmit={handleCreate} className="rounded-xl border border-border bg-background p-4">
          <p className="text-sm font-medium text-foreground">{t('create_new')}</p>
          <div className="mt-3 flex items-center gap-2">
            <Input
              value={label}
              onChange={e => setLabel(e.target.value)}
              placeholder={t('label_placeholder')}
              required
            />
            <Button type="submit" size="sm" disabled={creating}>
              <Plus />
              {creating ? t('generating') : t('generate')}
            </Button>
          </div>
        </form>

        <div>
          <p className="mb-2 flex items-center gap-1.5 text-sm font-medium text-foreground">
            <KeyRound className="size-4 text-muted-foreground" />
            {t('existing')}
          </p>
          {pats.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t('none')}</p>
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
                      {t('created_at', { date: p.created_at })}
                      {p.last_used_at ? ` · ${t('last_used', { date: p.last_used_at })}` : ` · ${t('never_used')}`}
                    </p>
                  </div>
                  {p.expires_at && (
                    <span className="shrink-0 text-xs text-muted-foreground">{t('expires', { date: p.expires_at })}</span>
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