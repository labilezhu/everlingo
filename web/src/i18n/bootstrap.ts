// 多入口 bootstrap：所有 HTML 入口（chatbot / editor / me / target-language /
// interface-language / web-console / login / self-service / pat）共用一个初始化流程。
// ref: docs/ADR/20260806-phase3-web-i18n-onboarding.md §4.2
//
// 顺序：
//   1. initI18n(navigator 启发值) → 立即可用（首屏加载占位文案可被翻译）
//   2. GET /api/user-profile/status → 若 interface_language_resolved 与启发值不同则
//      changeLanguage 校正（服务端值为最终生效值，可能是用户此前显式选写的）
//   3. 返回 status 供调用方决定 onboarding 跳转 / 正常渲染
import { i18n, initI18n } from './i18n';
import { detectBootstrapLang } from './detect';
import { apiFetchJson } from '@/services/apiFetch';
import type { ProfileStatus } from '@/types/profile';

export interface BootstrapResult {
  status: ProfileStatus | null;
}

export async function bootstrapI18n(): Promise<BootstrapResult> {
  await initI18n(detectBootstrapLang());
  // /login 未认证，请求 /api/user-profile/status 会 401 → apiFetch 触发 /login 重载死循环，
  // 且未登录也无法得知用户的已保存偏好，直接用 navigator 启发值即可。
  if (window.location.pathname === '/login' || window.location.pathname.startsWith('/login/')) {
    return { status: null };
  }
  try {
    const status = await apiFetchJson<ProfileStatus>('/api/user-profile/status');
    if (status.interface_language_resolved && status.interface_language_resolved !== i18n.language) {
      await i18n.changeLanguage(status.interface_language_resolved);
    }
    return { status };
  } catch {
    // 请求失败（如多用户拓扑未登录 / 服务不可达）时沿用启发值，不阻塞渲染
    return { status: null };
  }
}

// 切换界面语言后调用：写回 yaml 已由后端完成，前端即时切换无需刷新页面。
export function changeInterfaceLanguage(lang: string): Promise<unknown> {
  return i18n.changeLanguage(lang);
}

// 首屏加载占位文案（用启发值，避免 i18n 初始化完成前的闪烁）。
// 仅在 application bootstrap 最早阶段（initI18n 尚未 await 完成）渲染时使用。
export function bootstrapLoadingText(): string {
  const lang = detectBootstrapLang();
  return lang === 'zh-CN' ? '加载中…' : 'Loading…';
}

// onboarding 跳转目标：needs_setup=false → null（不跳转）。
// interface_language 为空 → step 1（选界面语言）；否则 → step 2（目标学习语言）。
export function onboardingTarget(status: ProfileStatus): string | null {
  if (!status.needs_setup) return null;
  if (!status.interface_language) return '/console/me/interface-language';
  return '/console/me/target-language';
}