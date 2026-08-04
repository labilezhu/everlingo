import { useEffect } from 'react';
import { apiFetchJson } from '@/services/apiFetch';

// ref: docs/ADR/20260804-web-cache-control.md — iOS PWA 后台/bfcache 恢复时的认证态复检。
// 从 bfcache/page-cache 复活时不会发顶层导航（服务端的 302→/login 不会触发），
// 因此这里在可见性变化 / pageshow(persisted) 时主动请求一次受保护接口；
// 若 401，apiFetchJson 会兜底跳 /login。简单单机部署无鉴权，恒 200，无副作用。
export function useAuthRecheck(): void {
  useEffect(() => {
    let pageshowFired = false;
    const onVisibility = async () => {
      if (document.visibilityState !== 'visible') return;
      try { await apiFetchJson('/api/user-profile/status'); } catch { /* 401 已跳转 */ }
    };
    const onPageshow = (e: PageTransitionEvent) => {
      if (pageshowFired) return;
      pageshowFired = true;
      if (e.persisted) void onVisibility();
    };
    document.addEventListener('visibilitychange', onVisibility);
    window.addEventListener('pageshow', onPageshow);
    return () => {
      document.removeEventListener('visibilitychange', onVisibility);
      window.removeEventListener('pageshow', onPageshow);
    };
  }, []);
}
