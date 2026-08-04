import { useEffect, useState } from 'react';
import { ArrowLeft, Languages, Loader2, RotateCcw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { apiFetch, apiFetchJson } from '@/services/apiFetch';
import { useAuthRecheck } from '@/services/useAuthRecheck';

// ref: docs/ADR/20260801-user-onboarding.md — 目标学习语言设置页与首次使用引导
// ref: docs/ADR/20260804-web-cache-control.md — 401 由 apiFetchJson 统一兜底跳 /login

interface LanguageEntry {
  code: string;
  name: string;
  is_default: boolean;
  vault_initialized: boolean | null;
  disabled: boolean;
  disabled_reason: string | null;
}

interface LanguageList {
  languages: LanguageEntry[];
  current_default: string;
}

interface ProfileStatus {
  target_language: string;
  is_valid: boolean;
  vault_initialized: boolean | null;
  needs_setup: boolean;
}

type LoadState = 'loading' | 'ready' | 'error';

export default function TargetLanguagePage() {
  const [loadState, setLoadState] = useState<LoadState>('loading');
  const [loadError, setLoadError] = useState('');
  const [list, setList] = useState<LanguageList | null>(null);
  const [needsSetup, setNeedsSetup] = useState(false);
  const [selected, setSelected] = useState('');
  const [saving, setSaving] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [saveMessage, setSaveMessage] = useState('');

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      apiFetchJson<ProfileStatus>('/api/user-profile/status'),
      apiFetchJson<LanguageList>('/api/target-language/list'),
    ])
      .then(([status, langs]) => {
        if (cancelled) return;
        setList(langs);
        setNeedsSetup(status.needs_setup);
        setSelected(langs.current_default);
        setLoadState('ready');
      })
      .catch(() => {
        if (cancelled) return;
        setLoadError('无法加载语言列表');
        setLoadState('error');
      });
    return () => { cancelled = true; };
  }, []);

  useAuthRecheck();

  const saveEnabled =
    selected !== '' &&
    !(list?.languages.find(l => l.code === selected)?.vault_initialized === null) &&
    !saving && !resetting;

  const resetEnabled =
    selected !== '' &&
    list?.languages.find(l => l.code === selected)?.vault_initialized === true &&
    !resetting && !saving;

  async function handleSave() {
    if (!selected) return;
    setSaving(true);
    setSaveMessage('');
    try {
      const resp = await apiFetch('/api/target-language/default', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ lang: selected }),
      });
      if (!resp.ok) {
        const detail = await resp.json().catch(() => null);
        setSaveMessage(detail?.detail || '保存失败');
        return;
      }
      const newList: LanguageList = await resp.json();
      setList(newList);
      setSaveMessage('已切换，对话已重置');
      setTimeout(() => { window.location.href = '/'; }, 800);
    } catch {
      setSaveMessage('无法连接服务器');
    } finally {
      setSaving(false);
    }
  }

  async function handleReset() {
    if (!selected) return;
    if (!window.confirm('"知识库规范" 下的文件，可能被替换，若你有修改过 "知识库规范"，文件可能丢失。')) return;
    setResetting(true);
    setSaveMessage('');
    try {
      const resp = await apiFetch('/api/target-language/reset-vault', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ lang: selected }),
      });
      if (!resp.ok) {
        const detail = await resp.json().catch(() => null);
        setSaveMessage(detail?.detail || '重新初始化失败');
        return;
      }
      const newList: LanguageList = await resp.json();
      setList(newList);
      setSaveMessage('已重新初始化知识库规范');
    } catch {
      setSaveMessage('无法连接服务器');
    } finally {
      setResetting(false);
    }
  }

  return (
    <div className="flex flex-col h-screen mx-auto max-w-md border-x border-border">
      <header className="flex items-center gap-2 px-3 py-2 md:px-4 md:py-3 border-b border-border bg-background shrink-0">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => { window.location.href = '/console/me'; }}
        >
          <ArrowLeft />
          <span className="hidden md:inline">Me</span>
        </Button>
        <h1 className="text-lg font-semibold text-foreground">目标学习语言</h1>
      </header>

      {needsSetup && loadState === 'ready' && (
        <div className="shrink-0 px-3 py-2 md:px-4 bg-primary/10 text-primary text-sm font-medium border-b border-border">
          请选定一个有效的目标学习语言并初始化笔记库
        </div>
      )}

      <main className="flex-1 overflow-y-auto px-3 py-4 md:px-4">
        {loadState === 'loading' && (
          <div className="flex items-center justify-center py-16 text-muted-foreground">
            <Loader2 className="size-5 animate-spin" />
          </div>
        )}

        {loadState === 'error' && (
          <div className="py-16 text-center text-destructive">{loadError}</div>
        )}

        {loadState === 'ready' && list && (
          <div className="space-y-2">
            {list.languages.map(lang => (
              <button
                key={lang.code}
                disabled={lang.disabled}
                className="flex items-center justify-between gap-3 w-full text-left rounded-xl border border-border bg-background px-4 py-3 transition-all outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 hover:bg-muted disabled:opacity-50 disabled:pointer-events-none disabled:hover:bg-background"
                onClick={() => { setSelected(lang.code); }}
              >
                <span className="flex items-center gap-3 min-w-0">
                  <span
                    className={`size-4 shrink-0 rounded-full border-2 ${
                      selected === lang.code
                        ? 'border-primary bg-primary'
                        : 'border-muted-foreground/50'
                    }`}
                  />
                  <span className="min-w-0">
                    <span className="block text-sm font-medium text-foreground">{lang.name}</span>
                    <span className="block text-xs text-muted-foreground">
                      {lang.disabled
                        ? lang.disabled_reason
                        : lang.vault_initialized
                          ? '笔记库已初始化'
                          : '笔记库未初始化'}
                    </span>
                  </span>
                </span>
                {lang.is_default && (
                  <span className="shrink-0 text-xs text-muted-foreground">默认</span>
                )}
              </button>
            ))}

            {saveMessage && (
              <div className="text-sm text-center py-2 text-primary">{saveMessage}</div>
            )}

            <div className="flex gap-2 mt-2">
              <Button
                variant="outline"
                className="flex-1"
                disabled={!resetEnabled}
                onClick={handleReset}
              >
                {resetting && <Loader2 className="size-4 animate-spin" />}
                <RotateCcw className="size-4" />
                重新初始化
              </Button>
              <Button
                className="flex-1"
                disabled={!saveEnabled}
                onClick={handleSave}
              >
                {saving && <Loader2 className="size-4 animate-spin" />}
                保存
              </Button>
            </div>
          </div>
        )}
      </main>

      {!needsSetup && loadState === 'ready' && (
        <footer className="shrink-0 border-t border-border px-3 py-3 md:px-4">
          <Button
            variant="ghost"
            className="w-full justify-start gap-2 text-muted-foreground"
            onClick={() => { window.location.href = '/'; }}
          >
            <Languages className="size-4" />
            返回聊天
          </Button>
        </footer>
      )}
    </div>
  );
}
