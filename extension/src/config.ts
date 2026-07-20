export const DEFAULT_API_BASE_URL = 'http://localhost:8000';
export const SERVER_URL_STORAGE_KEY = 'server_url';

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
