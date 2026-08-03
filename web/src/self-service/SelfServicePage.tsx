import { ArrowLeft, KeyRound, LogOut } from 'lucide-react';
import { Button } from '@/components/ui/button';

export default function SelfServicePage() {
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
          <span className="hidden md:inline">返回</span>
        </Button>
        <h1 className="text-lg font-semibold text-foreground">账号</h1>
      </header>

      <main className="flex-1 overflow-y-auto px-3 py-4 md:px-4 space-y-2">
        <button
          className="flex items-center gap-3 w-full text-left rounded-xl border border-border bg-background px-4 py-3 transition-all outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 hover:bg-muted"
          onClick={() => { window.location.href = '/self-service/pat'; }}
        >
          <KeyRound className="size-5 text-muted-foreground shrink-0" />
          <span className="min-w-0">
            <span className="block text-sm font-medium text-foreground">永久 Token（浏览器扩展用）</span>
            <span className="block text-xs text-muted-foreground">生成用于 Chrome 扩展 / curl 的长期访问凭证</span>
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
          退出登录
        </Button>
      </footer>
    </div>
  );
}
