import { useCallback, useEffect, useState } from 'react';
import {
  AlertTriangle,
  ArrowLeft,
  Cloud,
  GitBranch,
  History,
  Loader2,
  RefreshCw,
  Save,
  Send,
  Server,
  Upload,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { apiFetchJson } from '@/services/apiFetch';
import { useAuthRecheck } from '@/services/useAuthRecheck';
import type {
  BackupConfig,
  BackupLogResponse,
  BackupResultResponse,
  BackupStatus,
  BackupTestResponse,
} from '@/types/backup';

// ref: docs/ADR/20260810-vault-version-control.md — P3/P4 UI console 页
// /console/me/backup：状态 + 配置表单 + 操作（测试/快照/推送/拉取/hard reset）+ 历史。
// P4：支持 https_pat 凭证。PAT 输入框只在用户实际编辑时才随请求提交
// （pat + pat_changed=true），否则 omit 字段让后端保留原值——前端不留存真实 PAT。

type LoadState = 'loading' | 'ready' | 'error';
type ActionResult = { ok: boolean; text: string } | null;

const emptyConfig: BackupConfig = {
  enabled: false,
  remote_url: '',
  branch: 'main',
  commit_interval: 300,
  push_interval: 300,
  auth: { method: 'ssh', ssh_private_key_file: '', pat: '' },
};

export default function BackupPage() {
  const { t } = useTranslation('backup');
  const [loadState, setLoadState] = useState<LoadState>('loading');
  const [status, setStatus] = useState<BackupStatus | null>(null);
  const [config, setConfig] = useState<BackupConfig>(emptyConfig);
  const [log, setLog] = useState<BackupLogResponse | null>(null);
  const [saving, setSaving] = useState(false);
  const [action, setAction] = useState<string | null>(null);
  const [result, setResult] = useState<ActionResult>(null);
  const [patValue, setPatValue] = useState('');
  const [patEdited, setPatEdited] = useState(false);

  const loadAll = useCallback(async () => {
    try {
      const [st, cfg, lg] = await Promise.all([
        apiFetchJson<BackupStatus>('/api/backup/status'),
        apiFetchJson<BackupConfig>('/api/backup/config'),
        apiFetchJson<BackupLogResponse>('/api/backup/log?limit=20'),
      ]);
      setStatus(st);
      setConfig(cfg);
      setPatValue(cfg.auth.pat);
      setPatEdited(false);
      setLog(lg);
      setLoadState('ready');
    } catch {
      setLoadState('error');
    }
  }, []);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  useAuthRecheck();

  async function handleSave() {
    setSaving(true);
    setResult(null);
    try {
      const body: Record<string, unknown> = {
        enabled: config.enabled,
        remote_url: config.remote_url,
        branch: config.branch,
        method: config.auth.method,
        ssh_private_key_file: config.auth.ssh_private_key_file,
        push_interval: config.push_interval,
      };
      if (config.auth.method === 'https_pat' && patEdited) {
        body.pat = patValue;
        body.pat_changed = true;
      }
      const updated = await apiFetchJson<BackupConfig>('/api/backup/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      setConfig(updated);
      setPatValue(updated.auth.pat);
      setPatEdited(false);
      setResult({ ok: true, text: t('saved') });
    } catch (e) {
      const msg = e instanceof Error ? e.message : t('save_failed');
      setResult({ ok: false, text: msg });
    } finally {
      setSaving(false);
    }
  }

  async function runAction(kind: 'test' | 'snapshot' | 'push' | 'pull' | 'reset-hard') {
    if (kind === 'reset-hard') {
      if (!window.confirm(t('reset_hard_confirm'))) return;
    }
    setAction(kind);
    setResult(null);
    try {
      if (kind === 'test') {
        const r = await apiFetchJson<BackupTestResponse>('/api/backup/test', { method: 'POST' });
        setResult({ ok: r.ok, text: r.message });
      } else if (kind === 'snapshot' || kind === 'push') {
        const r = await apiFetchJson<{ ok: boolean }>(`/api/backup/${kind}`, { method: 'POST' });
        setResult({ ok: r.ok, text: r.ok ? t('action_succeeded') : t('action_failed') });
      } else {
        const r = await apiFetchJson<BackupResultResponse>(`/api/backup/${kind}`, { method: 'POST' });
        const extra = r.backup_branch ? ` · backup: ${r.backup_branch}` : '';
        setResult({ ok: r.ok, text: `${r.message}${extra}` });
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : t('action_failed');
      setResult({ ok: false, text: msg });
    } finally {
      setAction(null);
      void loadAll();
    }
  }

  return (
    <div className="flex flex-col h-screen mx-auto max-w-md border-x border-border">
      <header className="flex items-center gap-2 px-3 py-2 md:px-4 md:py-3 border-b border-border bg-background shrink-0">
        <Button variant="ghost" size="sm" onClick={() => { window.location.href = '/console/me'; }}>
          <ArrowLeft />
          <span className="hidden md:inline">{t('back')}</span>
        </Button>
        <h1 className="text-lg font-semibold text-foreground">{t('title')}</h1>
      </header>

      <main className="flex-1 overflow-y-auto px-3 py-4 md:px-4 space-y-4">
        {loadState === 'loading' && (
          <div className="flex items-center justify-center py-16 text-muted-foreground">
            <Loader2 className="size-5 animate-spin" />
          </div>
        )}

        {loadState === 'error' && (
          <div className="flex flex-col items-center gap-3 py-16 text-center">
            <p className="text-destructive">{t('cant_connect')}</p>
            <Button variant="outline" onClick={() => { setLoadState('loading'); void loadAll(); }}>
              <RefreshCw />
              Retry
            </Button>
          </div>
        )}

        {loadState === 'ready' && status && (
          <>
            {/* 状态卡 */}
            <section className="rounded-xl border border-border bg-background px-4 py-3">
              <h2 className="flex items-center gap-2 text-sm font-semibold text-foreground">
                <Server className="size-4 text-muted-foreground" />
                {t('status_title')}
              </h2>
              <dl className="mt-2 space-y-1 text-sm">
                <Row k={t('status_enabled')} v={t('config_enabled')} />
                <Row k={t('last_commit')} v={status.last_commit_at ?? t('never')} />
                <Row k={t('last_push')} v={status.last_push_at ?? t('never')} />
                <Row k={t('ahead') + '/' + t('behind')} v={`${status.ahead}/${status.behind}`} />
                <Row k={t('remote_url')} v={status.remote_url || '—'} />
                <Row k={t('branch')} v={status.branch} />
              </dl>
            </section>

            {/* 配置表单 */}
            <section className="rounded-xl border border-border bg-background px-4 py-3">
              <h2 className="flex items-center gap-2 text-sm font-semibold text-foreground">
                <Cloud className="size-4 text-muted-foreground" />
                {t('config_title')}
              </h2>
              <div className="mt-3 space-y-3">
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    className="size-4 accent-primary"
                    checked={config.enabled}
                    onChange={e => setConfig({ ...config, enabled: e.target.checked })}
                  />
                  {t('config_enabled')}
                </label>
                <div>
                  <label className="block text-xs text-muted-foreground">{t('remote_url_label')}</label>
                  <Input
                    value={config.remote_url}
                    placeholder={t('remote_url_placeholder')}
                    onChange={e => setConfig({ ...config, remote_url: e.target.value })}
                  />
                </div>
                <div>
                  <label className="block text-xs text-muted-foreground">{t('branch_label')}</label>
                  <Input
                    value={config.branch}
                    onChange={e => setConfig({ ...config, branch: e.target.value })}
                  />
                </div>
                <div>
                  <label className="block text-xs text-muted-foreground">{t('method_label')}</label>
                  <select
                    className="h-8 w-full rounded-lg border border-input bg-transparent px-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
                    value={config.auth.method}
                    onChange={e =>
                      setConfig({
                        ...config,
                        auth: {
                          ...config.auth,
                          method: e.target.value as BackupConfig['auth']['method'],
                        },
                      })
                    }
                  >
                    <option value="ssh">{t('method_ssh')}</option>
                    <option value="https_pat">{t('method_https_pat')}</option>
                    <option value="https_none">{t('method_https_none')}</option>
                  </select>
                </div>
                {config.auth.method === 'ssh' && (
                  <div>
                    <label className="block text-xs text-muted-foreground">{t('ssh_key_label')}</label>
                    <Input
                      value={config.auth.ssh_private_key_file}
                      placeholder={t('ssh_key_placeholder')}
                      onChange={e =>
                        setConfig({
                          ...config,
                          auth: { ...config.auth, ssh_private_key_file: e.target.value },
                        })
                      }
                    />
                  </div>
                )}
                {config.auth.method === 'https_pat' && (
                  <div>
                    <label className="block text-xs text-muted-foreground">{t('pat_label')}</label>
                    <Input
                      value={patValue}
                      placeholder={t('pat_placeholder')}
                      onChange={e => {
                        setPatValue(e.target.value);
                        setPatEdited(true);
                      }}
                    />
                  </div>
                )}
                <Button className="w-full" disabled={saving} onClick={handleSave}>
                  {saving ? <Loader2 className="size-4 animate-spin" /> : <Save className="size-4" />}
                  {t('save')}
                </Button>
              </div>
            </section>

            {/* 操作 */}
            <section className="rounded-xl border border-border bg-background px-4 py-3">
              <h2 className="flex items-center gap-2 text-sm font-semibold text-foreground">
                <GitBranch className="size-4 text-muted-foreground" />
                {t('actions_title')}
              </h2>
              <div className="mt-3 grid grid-cols-2 gap-2">
                <Button variant="outline" disabled={action !== null} onClick={() => void runAction('test')}>
                  {action === 'test' ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />}
                  {t('action_test')}
                </Button>
                <Button variant="outline" disabled={action !== null} onClick={() => void runAction('snapshot')}>
                  {action === 'snapshot' ? <Loader2 className="size-4 animate-spin" /> : <Save className="size-4" />}
                  {t('action_snapshot')}
                </Button>
                <Button variant="outline" disabled={action !== null} onClick={() => void runAction('push')}>
                  {action === 'push' ? <Loader2 className="size-4 animate-spin" /> : <Upload className="size-4" />}
                  {t('action_push')}
                </Button>
                <Button variant="outline" disabled={action !== null} onClick={() => void runAction('pull')}>
                  {action === 'pull' ? <Loader2 className="size-4 animate-spin" /> : <RefreshCw className="size-4" />}
                  {t('action_pull')}
                </Button>
                <Button
                  variant="destructive"
                  className="col-span-2"
                  disabled={action !== null}
                  onClick={() => void runAction('reset-hard')}
                >
                  {action === 'reset-hard' ? <Loader2 className="size-4 animate-spin" /> : <AlertTriangle className="size-4" />}
                  {t('action_reset_hard')}
                </Button>
              </div>
              {result && (
                <p className={`mt-2 text-sm ${result.ok ? 'text-primary' : 'text-destructive'}`}>{result.text}</p>
              )}
            </section>

            {/* 历史 */}
            <section className="rounded-xl border border-border bg-background px-4 py-3">
              <h2 className="flex items-center gap-2 text-sm font-semibold text-foreground">
                <History className="size-4 text-muted-foreground" />
                {t('history_title')}
              </h2>
              {log && log.commits.length > 0 ? (
                <ul className="mt-2 space-y-1">
                  {log.commits.map(c => (
                    <li key={c.hash} className="flex items-baseline gap-2 text-sm">
                      <span className="font-mono text-xs text-muted-foreground">{c.hash.slice(0, 8)}</span>
                      <span className="min-w-0 flex-1 truncate text-foreground">{c.message}</span>
                      <span className="shrink-0 text-xs text-muted-foreground">{c.time}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-2 text-sm text-muted-foreground">{t('history_empty')}</p>
              )}
            </section>
          </>
        )}
      </main>
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between gap-2">
      <dt className="text-muted-foreground">{k}</dt>
      <dd className="text-right text-foreground">{v}</dd>
    </div>
  );
}
