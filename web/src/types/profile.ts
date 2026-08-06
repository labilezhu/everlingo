// GET /api/user-profile/status 响应类型。
// ref: docs/ADR/20260806-phase3-web-i18n-onboarding.md §4.6
export interface AvailableInterfaceLanguage {
  code: string;
  name: string;
}

export interface ProfileStatus {
  target_language: string;
  is_valid: boolean;
  vault_initialized: boolean | null;
  needs_setup: boolean;
  interface_language: string;
  interface_language_resolved: string;
  available_interface_languages: AvailableInterfaceLanguage[];
}
