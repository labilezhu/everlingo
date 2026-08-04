import { Component, type ReactNode } from 'react';
import { Button } from '@/components/ui/button';
import { redirectToLogin } from '@/services/apiFetch';

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
      return (
        <div className="flex min-h-screen items-center justify-center bg-background px-4">
          <div className="w-full max-w-sm rounded-xl border border-border bg-background p-6 text-center shadow-sm">
            <h1 className="text-lg font-semibold text-foreground mb-2">页面遇到了一点问题</h1>
            <p className="text-sm text-muted-foreground mb-4">
              可能是网络波动或登录状态已失效。请重新加载，必要时重新登录。
            </p>
            <div className="flex flex-col gap-2">
              <Button onClick={() => window.location.reload()}>重新加载</Button>
              <Button variant="outline" onClick={() => redirectToLogin()}>
                重新登录
              </Button>
            </div>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}