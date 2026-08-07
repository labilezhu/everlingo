export const DEFAULT_API_BASE_URL = 'http://localhost:8000';
export const SERVER_URL_STORAGE_KEY = 'server_url';
export const SERVER_TOKEN_STORAGE_KEY = 'server_token';
export const INTERFACE_LANGUAGE_STORAGE_KEY = 'interface_language';

export class UrlFormatError extends Error {
  constructor() {
    super('URL must start with http:// or https://');
    this.name = 'UrlFormatError';
  }
}

export async function getStoredInterfaceLanguage(): Promise<string> {
  const { [INTERFACE_LANGUAGE_STORAGE_KEY]: stored } = await chrome.storage.local.get(
    INTERFACE_LANGUAGE_STORAGE_KEY,
  );
  return typeof stored === 'string' ? stored : '';
}

export async function setStoredInterfaceLanguage(lang: string): Promise<void> {
  if (!lang) return;
  await chrome.storage.local.set({ [INTERFACE_LANGUAGE_STORAGE_KEY]: lang });
}

export function normalizeUrl(input: string): string {
  let url = input.trim();
  if (!url) return DEFAULT_API_BASE_URL;
  if (!/^https?:\/\//i.test(url)) {
    throw new UrlFormatError();
  }
  url = url.replace(/\/+$/, '');
  return url;
}

export async function getApiBaseUrl(): Promise<string> {
  const { [SERVER_URL_STORAGE_KEY]: stored } = await chrome.storage.local.get(SERVER_URL_STORAGE_KEY);
  if (typeof stored === 'string' && stored) {
    try {
      return normalizeUrl(stored);
    } catch {
      return DEFAULT_API_BASE_URL;
    }
  }
  return DEFAULT_API_BASE_URL;
}

export async function getApiToken(): Promise<string> {
  const { [SERVER_TOKEN_STORAGE_KEY]: stored } = await chrome.storage.local.get(SERVER_TOKEN_STORAGE_KEY);
  return typeof stored === 'string' ? stored : '';
}

export function buildBearerHeader(token: string): string | null {
  const t = token.trim();
  if (!t) return null;
  return 'Bearer ' + t;
}

export async function getApiConfig(): Promise<{ baseUrl: string; authHeader: string | null }> {
  const [baseUrl, token] = await Promise.all([
    getApiBaseUrl(),
    getApiToken(),
  ]);
  return {
    baseUrl,
    authHeader: buildBearerHeader(token),
  };
}
