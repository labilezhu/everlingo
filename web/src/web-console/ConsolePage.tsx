import { MessageSquare, Settings2 } from 'lucide-react';
import WechatChannelAdmin from './WechatChannelAdmin';
import { Button } from '@/components/ui/button';

const WECHAT_ADMIN_PATH = '/web-console/plugins/channels/wechat_channel/admin';

function ChannelsHome() {
  return (
    <div className="p-4 space-y-2">
      <h2 className="text-sm font-semibold text-foreground px-1">Channels</h2>
      <button
        className="flex items-center gap-3 w-full text-left rounded-xl border border-border bg-background px-4 py-3 transition-all outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 hover:bg-muted"
        onClick={() => { window.location.href = WECHAT_ADMIN_PATH; }}
      >
        <MessageSquare className="size-5 text-muted-foreground shrink-0" />
        <span className="min-w-0">
          <span className="block text-sm font-medium text-foreground">Wechat channel</span>
          <span className="block text-xs text-muted-foreground">登录 / 启停 / 扫码管理</span>
        </span>
      </button>
    </div>
  );
}

export default function ConsolePage() {
  const path = window.location.pathname;
  const inWechatAdmin = path === WECHAT_ADMIN_PATH || path.startsWith(WECHAT_ADMIN_PATH + '/');

  return (
    <div className="flex flex-col h-screen mx-auto max-w-md border-x border-border">
      <header className="flex items-center gap-2 px-3 py-2 md:px-4 md:py-3 border-b border-border bg-background shrink-0">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => { window.location.href = inWechatAdmin ? '/web-console' : '/me'; }}
        >
          <Settings2 className="rotate-180" />
        </Button>
        <h1 className="text-lg font-semibold text-foreground">
          {inWechatAdmin ? 'Wechat channel' : 'Workspace Console'}
        </h1>
      </header>

      <main className="flex-1 overflow-y-auto">
        {inWechatAdmin ? <WechatChannelAdmin /> : <ChannelsHome />}
      </main>
    </div>
  );
}
