import { StrictMode, useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import ChatWindow from './components/ChatWindow';
import './index.css';

// ref: docs/ADR/20260801-user-onboarding.md §5 — 首次使用强制跳转
// chatbot 首页加载时先检查默认目标学习语言配置；needs_setup=true 则跳转设置页。

interface ProfileStatus {
  target_language: string;
  is_valid: boolean;
  vault_initialized: boolean | null;
  needs_setup: boolean;
}

type BootstrapState = 'checking' | 'ready';

function Root() {
  const [state, setState] = useState<BootstrapState>('checking');

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const resp = await fetch('/api/user-profile/status');
        const status: ProfileStatus = await resp.json();
        if (cancelled) return;
        if (status.needs_setup) {
          window.location.href = '/console/me/target-language';
          return;
        }
        setState('ready');
      } catch {
        if (cancelled) return;
        setState('ready');
      }
    })();
    return () => { cancelled = true; };
  }, []);

  if (state === 'checking') {
    return (
      <div className="flex items-center justify-center h-screen text-muted-foreground">
        加载中…
      </div>
    );
  }

  return <ChatWindow />;
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Root />
  </StrictMode>,
);
