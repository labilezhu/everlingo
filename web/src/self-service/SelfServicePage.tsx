import { useTranslation } from 'react-i18next';
import { ArrowLeft, KeyRound, LogOut } from 'lucide-react';
import { Button } from '@/components/ui/button';

export default function SelfServicePage() {
  const { t } = useTranslation('self-service');

  function goBack() {
    if (window.history.length > 1) {
      window.history.back();
    } else {
      window.location.href = '/';
    }
  }

  return (
    <div className="flex flex-col h-screen mx-auto max-w-md border-x border-border">
      <header className="flex items-center gap-2 px-3 py-2 md:px-4 md:py-3 border-b border-border bg-background shrink-0">
        <Button variant="ghost" size="sm" onClick={goBack}>
          <ArrowLeft />
          <span className="hidden md:inline">{t('back')}</span>
        </Button>
        <h1 className="text-lg font-semibold text-foreground">{t('account')}</h1>
      </header>

      <main className="flex-1 overflow-y-auto px-3 py-4 md:px-4 space-y-2">
        <button
          className="flex items-center gap-3 w-full text-left rounded-xl border border-border bg-background px-4 py-3 transition-all outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 hover:bg-muted"
          onClick={() => { window.location.href = '/self-service/pat'; }}
        >
          <KeyRound className="size-5 text-muted-foreground shrink-0" />
          <span className="min-w-0">
            <span className="block text-sm font-medium text-foreground">{t('pat_title')}</span>
            <span className="block text-xs text-muted-foreground">{t('pat_desc')}</span>
          </span>
        </button>
      </main>

      <footer className="shrink-0 border-t border-border px-3 pt-3 pb-[calc(1.5rem+env(safe-area-inset-bottom))] md:px-4 md:py-3">
        <Button
          variant="ghost"
          className="w-full justify-start gap-2 text-muted-foreground"
          onClick={() => { window.location.href = '/logout'; }}
        >
          <LogOut className="size-4" />
          {t('logout')}
        </Button>
      </footer>
    </div>
  );
}