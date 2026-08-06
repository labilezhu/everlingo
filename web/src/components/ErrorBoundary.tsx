import { Component, type ReactNode } from 'react';
import { Button } from '@/components/ui/button';
import { redirectToLogin } from '@/services/apiFetch';
import { i18n } from '@/i18n/i18n';

// ref: docs/ADR/20260804-web-cache-control.md — 全局兜底：避免 React 渲染异常导致整棵树卸载白屏。
interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch() {
    // 默认不外发，保留错误详情供调试台查看
  }

  render() {
    if (this.state.hasError) {
      const t = (key: string) => i18n.t(key, { ns: 'common' });
      return (
        <div className="flex min-h-screen items-center justify-center bg-background px-4">
          <div className="w-full max-w-sm rounded-xl border border-border bg-background p-6 text-center shadow-sm">
            <h1 className="text-lg font-semibold text-foreground mb-2">{t('page_error')}</h1>
            <p className="text-sm text-muted-foreground mb-4">
              {t('page_error_hint')}
            </p>
            <div className="flex flex-col gap-2">
              <Button onClick={() => window.location.reload()}>{t('reload')}</Button>
              <Button variant="outline" onClick={() => redirectToLogin()}>
                {t('re_login')}
              </Button>
            </div>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}