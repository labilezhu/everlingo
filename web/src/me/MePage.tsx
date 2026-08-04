import { ArrowLeft, Languages, Settings2, UserRound } from 'lucide-react';
import { Button } from '@/components/ui/button';

const entries = [
  {
    title: '目标学习语言',
    description: '选择默认学习语言并初始化笔记库',
    href: '/console/me/target-language',
    icon: Languages,
  },
  {
    title: 'Workspace Console',
    description: '频道与网关管理',
    href: '/console/web-console',
    icon: Settings2,
  },
];

export default function MePage() {
  return (
    <div className="flex flex-col h-screen mx-auto max-w-md border-x border-border">
      <header className="flex items-center gap-2 px-3 py-2 md:px-4 md:py-3 border-b border-border bg-background shrink-0">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => { window.location.href = '/'; }}
        >
          <ArrowLeft />
          <span className="hidden md:inline">聊天</span>
        </Button>
        <h1 className="text-lg font-semibold text-foreground">Me</h1>
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
          账号
        </Button>
        <div className="mt-2 px-3 text-xs text-muted-foreground/60">
          EverLingo 版本： 0.1.1-rc.2
        </div>
      </footer>
    </div>
  );
}
