export const DEFAULT_API_BASE_URL = 'http://localhost:8000';
export const SERVER_URL_STORAGE_KEY = 'server_url';
export const SERVER_USERNAME_STORAGE_KEY = 'server_username';
export const SERVER_PASSWORD_STORAGE_KEY = 'server_password';

export function normalizeUrl(input: string): string {
  let url = input.trim();
  if (!url) return DEFAULT_API_BASE_URL;
  if (!/^https?:\/\//i.test(url)) {
    throw new Error('URL 必须以 http:// 或 https:// 开头');
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

export async function getApiAuth(): Promise<{ username: string; password: string }> {
  const items = await chrome.storage.local.get([SERVER_USERNAME_STORAGE_KEY, SERVER_PASSWORD_STORAGE_KEY]);
  return {
    username: typeof items[SERVER_USERNAME_STORAGE_KEY] === 'string' ? items[SERVER_USERNAME_STORAGE_KEY] : '',
    password: typeof items[SERVER_PASSWORD_STORAGE_KEY] === 'string' ? items[SERVER_PASSWORD_STORAGE_KEY] : '',
  };
}

export function buildBasicAuthHeader(username: string, password: string): string | null {
  const u = username.trim();
  if (!u) return null;
  return 'Basic ' + btoa(unescape(encodeURIComponent(`${u}:${password}`)));
}

export async function getApiConfig(): Promise<{ baseUrl: string; authHeader: string | null }> {
  const [baseUrl, { username, password }] = await Promise.all([
    getApiBaseUrl(),
    getApiAuth(),
  ]);
  return {
    baseUrl,
    authHeader: buildBasicAuthHeader(username, password),
  };
}
