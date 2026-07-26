import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { EventSourceMessage } from '@microsoft/fetch-event-source';

let onmessage: ((msg: EventSourceMessage) => void) | null = null;
let onerror: ((err: unknown) => number | null | undefined | void) | null = null;
let abortSignal: AbortSignal | null = null;
let passedHeaders: Record<string, string> | undefined;

vi.mock('@microsoft/fetch-event-source', () => ({
  fetchEventSource(
    _url: string,
    opts: {
      signal?: AbortSignal;
      headers?: Record<string, string>;
      onmessage?: (msg: EventSourceMessage) => void;
      onerror?: (err: unknown) => number | null | undefined | void;
    },
  ) {
    onmessage = opts.onmessage ?? null;
    onerror = opts.onerror ?? null;
    abortSignal = opts.signal ?? null;
    passedHeaders = opts.headers;
  },
}));

import { sendEnvelope, connectSSE } from './sseClient';

beforeEach(() => {
  onmessage = null;
  onerror = null;
  abortSignal = null;
  passedHeaders = undefined;
});

describe('sendEnvelope', () => {
  it('sends POST with JSON body', async () => {
    const mockFetch = vi.fn().mockResolvedValue({ ok: true });
    vi.stubGlobal('fetch', mockFetch);
    const env = { schema_version: 1, task: 'translate' } as any;
    await sendEnvelope('http://localhost:8000', 'sid-1', env);
    expect(mockFetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/session/sid-1/message',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ envelope: env }),
      },
    );
  });

  it('includes Authorization header when authHeader provided', async () => {
    const mockFetch = vi.fn().mockResolvedValue({ ok: true });
    vi.stubGlobal('fetch', mockFetch);
    const env = { schema_version: 1 } as any;
    await sendEnvelope('http://localhost:8000', 'sid-1', env, 'Basic dXNlcjpwYXNz');
    expect(mockFetch).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: 'Basic dXNlcjpwYXNz',
        }),
      }),
    );
  });

  it('throws when response not ok', async () => {
    const mockFetch = vi.fn().mockResolvedValue({ ok: false });
    vi.stubGlobal('fetch', mockFetch);
    await expect(sendEnvelope('http://localhost:8000', 'sid-1', {} as any))
      .rejects.toThrow('Failed to send envelope');
  });
});

describe('connectSSE', () => {
  it('passes Authorization header to fetchEventSource', () => {
    const cleanup = connectSSE(
      'http://localhost:8000',
      'sid-1',
      vi.fn(),
      vi.fn(),
      'Basic dXNlcjpwYXNz',
    );
    expect(passedHeaders).toEqual({ Authorization: 'Basic dXNlcjpwYXNz' });
    cleanup();
  });

  it('does not set Authorization header when authHeader is null', () => {
    connectSSE('http://localhost:8000', 'sid-1', vi.fn(), vi.fn(), null);
    expect(passedHeaders).toEqual({});
  });

  it('dispatches message events to onEvent callback', () => {
    const onEvent = vi.fn();
    connectSSE('http://localhost:8000', 'sid-1', onEvent, vi.fn());
    onmessage!({ id: '', event: 'message', data: '{"text":"hello"}' });
    expect(onEvent).toHaveBeenCalledWith({
      type: 'message',
      data: { text: 'hello' },
    });
  });

  it('dispatches typing_hint events to onEvent callback', () => {
    const onEvent = vi.fn();
    connectSSE('http://localhost:8000', 'sid-1', onEvent, vi.fn());
    onmessage!({ id: '', event: 'typing_hint', data: '{"typing":true}' });
    expect(onEvent).toHaveBeenCalledWith({
      type: 'typing_hint',
      data: { typing: true },
    });
  });

  it('dispatches sound events to onEvent callback', () => {
    const onEvent = vi.fn();
    connectSSE('http://localhost:8000', 'sid-1', onEvent, vi.fn());
    onmessage!({ id: '', event: 'sound', data: '{"audio":"test"}' });
    expect(onEvent).toHaveBeenCalledWith({
      type: 'sound',
      data: { audio: 'test' },
    });
  });

  it('calls onError when error occurs', () => {
    const onError = vi.fn();
    connectSSE('http://localhost:8000', 'sid-1', vi.fn(), onError, undefined);
    onerror!('test error');
    expect(onError).toHaveBeenCalledOnce();
  });

  it('cleanup aborts the connection', () => {
    const cleanup = connectSSE('http://localhost:8000', 'sid-1', vi.fn(), vi.fn());
    expect(abortSignal!.aborted).toBe(false);
    cleanup();
    expect(abortSignal!.aborted).toBe(true);
  });

  it('skips invalid JSON in message data', () => {
    const onEvent = vi.fn();
    connectSSE('http://localhost:8000', 'sid-1', onEvent, vi.fn());
    onmessage!({ id: '', event: 'message', data: 'not json' });
    expect(onEvent).not.toHaveBeenCalled();
  });
});