import { useEffect, useState } from 'react';
import { ArrowLeft, Globe, Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { apiFetch, apiFetchJson } from '@/services/apiFetch';
import { changeInterfaceLanguage } from '@/i18n/bootstrap';
import { useAuthRecheck } from '@/services/useAuthRecheck';
import type { ProfileStatus } from '@/types/profile';

// ref: docs/ADR/20260806-phase3-web-i18n-onboarding.md §4.3 — onboarding step 1：
// 独立页面 /console/me/interface-language。首次引导（needs_setup 且 interface_language
// 空）时强制跳转至此；Me 页主动修改界面语言时同样复用本页。选定 → POST 写 yaml →
// 前端 changeLanguage 即时切换 → 重定向到 step 2（/console/me/target-language）。

type LoadState = 'loading' | 'ready' | 'error';

export default function InterfaceLanguagePage() {
  const { t } = useTranslation('onboarding');
  const [loadState, setLoadState] = useState<LoadState>('loading');
  const [avail, setAvail] = useState<ProfileStatus['available_interface_languages']>([]);
  const [needsSetup, setNeedsSetup] = useState(false);
  const [selected, setSelected] = useState('');
  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState('');

  useEffect(() => {
    let cancelled = false;
    apiFetchJson<ProfileStatus>('/api/user-profile/status')
      .then(status => {
        if (cancelled) return;
        setAvail(status.available_interface_languages);
        setNeedsSetup(status.needs_setup);
        setSelected(status.interface_language || status.interface_language_resolved);
        setLoadState('ready');
      })
      .catch(() => {
        if (cancelled) return;
        setLoadState('error');
      });
    return () => { cancelled = true; };
  }, []);

  useAuthRecheck();

  const saveEnabled = selected !== '' && !saving;

  async function handleSave() {
    if (!selected) return;
    setSaving(true);
    setSaveMessage('');
    try {
      const resp = await apiFetch('/api/user-profile/interface-language', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ lang: selected }),
      });
      if (!resp.ok) {
        const detail = await resp.json().catch(() => null);
        setSaveMessage(detail?.detail || t('save_failed'));
        return;
      }
      await changeInterfaceLanguage(selected);
      if (needsSetup) {
        setTimeout(() => { window.location.href = '/console/me/target-language'; }, 400);
      } else {
        setSaveMessage(t('switched'));
        setTimeout(() => { window.location.href = '/console/me'; }, 800);
      }
    } catch {
      setSaveMessage(t('cant_connect'));
    } finally {
      setSaving(false);
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
          <span className="hidden md:inline">{t('me')}</span>
        </Button>
        <h1 className="text-lg font-semibold text-foreground">{t('interface_title')}</h1>
      </header>

      {needsSetup && loadState === 'ready' && (
        <div className="shrink-0 px-3 py-2 md:px-4 bg-primary/10 text-primary text-sm font-medium border-b border-border">
          {t('interface_guidance')}
        </div>
      )}

      <main className="flex-1 overflow-y-auto px-3 py-4 md:px-4">
        {loadState === 'loading' && (
          <div className="flex items-center justify-center py-16 text-muted-foreground">
            <Loader2 className="size-5 animate-spin" />
          </div>
        )}

        {loadState === 'error' && (
          <div className="py-16 text-center text-destructive">{t('load_error')}</div>
        )}

        {loadState === 'ready' && (
          <div className="space-y-2">
            <p className="text-sm text-muted-foreground">{t('interface_subtitle')}</p>
            {avail.map(lang => (
              <button
                key={lang.code}
                className="flex items-center justify-between gap-3 w-full text-left rounded-xl border border-border bg-background px-4 py-3 transition-all outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 hover:bg-muted"
                onClick={() => setSelected(lang.code)}
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
                    <span className="block text-xs text-muted-foreground">{lang.code}</span>
                  </span>
                </span>
                {selected === lang.code && (
                  <span className="shrink-0 text-xs text-muted-foreground">{t('selected')}</span>
                )}
              </button>
            ))}

            {saveMessage && (
              <div className="text-sm text-center py-2 text-primary">{saveMessage}</div>
            )}

            <div className="flex gap-2 mt-2">
              <Button className="flex-1" disabled={!saveEnabled} onClick={handleSave}>
                {saving && <Loader2 className="size-4 animate-spin" />}
                <Globe className="size-4" />
                {t('save')}
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
            onClick={() => { window.location.href = '/console/me'; }}
          >
            <Globe className="size-4" />
            {t('me')}
          </Button>
        </footer>
      )}
    </div>
  );
}