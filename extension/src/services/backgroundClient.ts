export interface GetSessionResponse {
  sessionId: string;
  fresh: boolean;
  tabId: number;
  error?: boolean;
}

export async function getSession(): Promise<GetSessionResponse> {
  return new Promise((resolve, reject) => {
    chrome.runtime.sendMessage({ type: 'GET_SESSION' }, (response: unknown) => {
      const r = response as GetSessionResponse | undefined;
      if (!r || r.error || !r.sessionId) {
        reject(new Error('GET_SESSION failed'));
        return;
      }
      resolve(r);
    });
  });
}
