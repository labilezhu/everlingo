import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import ChatWindow from './components/ChatWindow';
import ErrorBoundary from './components/ErrorBoundary';
import { useAuthRecheck } from './services/useAuthRecheck';
import { bootstrapI18n, onboardingTarget, bootstrapLoadingText, setPageTitle } from './i18n/bootstrap';
import './index.css';

// ref: docs/ADR/20260801-user-onboarding.md §5 — 首次使用强制跳转
// ref: docs/ADR/20260806-phase3-web-i18n-onboarding.md §4.2/§4.4 — bootstrap 后按
// needs_setup 分支：interface_language 空 → step 1；否则 → step 2。

function Root() {
  useAuthRecheck();
  return <ChatWindow />;
}

async function boot() {
  const root = createRoot(document.getElementById('root')!);
  root.render(<div className="flex items-center justify-center h-screen text-muted-foreground">{bootstrapLoadingText()}</div>);
  const { status } = await bootstrapI18n();
  setPageTitle('chatbot', 'page_title');
  if (status) {
    const target = onboardingTarget(status);
    if (target) {
      window.location.href = target;
      return;
    }
  }
  root.render(
    <StrictMode>
      <ErrorBoundary>
        <Root />
      </ErrorBoundary>
    </StrictMode>,
  );
}

void boot();