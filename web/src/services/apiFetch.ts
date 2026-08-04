// ref: docs/ADR/20260804-web-cache-control.md — 统一 fetch 包装：
// - 全局 401 兜底 → 跳 /login（多用户部署下 JWT/cookie 过期）
// - 非 2xx 抛出结构化错误，供调用方展示
//
// 简单单机部署（无 ws-router）不存在 /login 且不会返回 401，因此本包装不会误跳。

let redirecting = false;

export class ApiError extends Error {
  status: number;
  code: string | null;
  detail: unknown;

  constructor(status: number, message: string, code: string | null = null, detail: unknown = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.detail = detail;
  }
}

function isLocalRedirect(url: string): boolean {
  return url.startsWith('/') || url.startsWith(window.location.origin);
}

function isLoginPath(path: string): boolean {
  return path === '/login' || path.startsWith('/login/');
}

export function redirectToLogin(): void {
  if (redirecting) return;
  redirecting = true;
  const current = window.location.pathname;
  const next = isLoginPath(current) ? current : '/login';
  window.location.replace(next);
}

export async function apiFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const response = await fetch(input, init);

  if (response.status === 401 && !isLoginPath(response.url)) {
    redirectToLogin();
    throw new ApiError(401, '登录已过期，请重新登录');
  }

  return response;
}

export async function apiFetchJson<T>(input: RequestInfo | URL, init?: RequestInit): Promise<T> {
  const res = await apiFetch(input, init);
  if (!res.ok) {
    let code: string | null = null;
    let detail: unknown = null;
    let message = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (body?.error?.code) code = body.error.code;
      if (body?.error?.message) message = body.error.message;
      if (body?.detail) {
        detail = body.detail;
        if (typeof body.detail === 'string') message = body.detail;
      }
    } catch { /* fall through */ }
    throw new ApiError(res.status, message, code, detail);
  }
  return res.json() as Promise<T>;
}
