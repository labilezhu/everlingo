export interface GetSessionResponse {
  sessionId: string;
  fresh: boolean;
  tabId: number;
  error?: boolean;
}

export async function getSession(): Promise<GetSessionResponse> {
  return new Promise((resolve) => {
    chrome.runtime.sendMessage({ type: 'GET_SESSION' }, (response: unknown) => {
      resolve(response as GetSessionResponse);
    });
  });
}
