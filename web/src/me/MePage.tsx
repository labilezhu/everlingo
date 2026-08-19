import { useEffect, useState } from 'react';
import { ArrowLeft, Cloud, Languages, Settings2, UserRound, Globe } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { apiFetchJson } from '@/services/apiFetch';
import type { ProfileStatus } from '@/types/profile';

export default function MePage() {
  const { t } = useTranslation('me');
  const [currentInterface, setCurrentInterface] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiFetchJson<ProfileStatus>('/api/user-profile/status')
      .then(status => {
        if (cancelled) return;
        const found = status.available_interface_languages.find(
          l => l.code === status.interface_language_resolved,
        );
        setCurrentInterface(found?.name ?? status.interface_language_resolved);
      })
      .catch(() => { /* 单机拓扑无鉴权，忽略失败 */ });
    return () => { cancelled = true; };
  }, []);

  const entries = [
    {
      title: t('target_language'),
      description: t('target_language_desc'),
      href: '/console/me/target-language',
      icon: Languages,
    },
    {
      title: t('interface_language'),
      description: currentInterface ? `${t('interface_language_desc')} · ${currentInterface}` : t('interface_language_desc'),
      href: '/console/me/interface-language',
      icon: Globe,
    },
    {
      title: t('workspace_console'),
      description: t('workspace_console_desc'),
      href: '/console/web-console',
      icon: Settings2,
    },
    {
      title: t('backup'),
      description: t('backup_desc'),
      href: '/console/me/backup',
      icon: Cloud,
    },
  ];

  return (
    <div className="flex flex-col h-screen mx-auto max-w-md border-x border-border">
      <header className="flex items-center gap-2 px-3 py-2 md:px-4 md:py-3 border-b border-border bg-background shrink-0">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => { window.location.href = '/'; }}
        >
          <ArrowLeft />
          <span className="hidden md:inline">{t('back_to_chat')}</span>
        </Button>
        <h1 className="text-lg font-semibold text-foreground">{t('title')}</h1>
      </header>

      <main className="flex-1 overflow-y-auto px-3 py-4 md:px-4 space-y-2">
        {entries.map(e => (
          <button
            key={e.href}
            className="flex items-center gap-3 w-full text-left rounded-xl border border-border bg-background px-4 py-3 transition-all outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 hover:bg-muted"
            onClick={() => { window.location.href = e.href; }}
          >
            <e.icon className="size-5 text-muted-foreground shrink-0" />
            <span className="min-w-0">
              <span className="block text-sm font-medium text-foreground">{e.title}</span>
              <span className="block text-xs text-muted-foreground">{e.description}</span>
            </span>
          </button>
        ))}
      </main>

      <footer className="shrink-0 border-t border-border px-3 pt-3 pb-[calc(1.5rem+env(safe-area-inset-bottom))] md:px-4 md:py-3">
        <Button
          variant="ghost"
          className="w-full justify-start gap-2 text-muted-foreground"
          onClick={() => { window.location.href = '/self-service'; }}
        >
          <UserRound className="size-4" />
          {t('account')}
        </Button>
        <div className="mt-2 px-3 text-xs text-muted-foreground/60">
          {t('version', { version: '0.1.2' })}
        </div>
      </footer>
    </div>
  );
}