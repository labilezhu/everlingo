import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { EventSourceMessage } from '@microsoft/fetch-event-source';

let onmessage: ((msg: EventSourceMessage) => void) | null = null;
let onerror: ((err: unknown) => number | null | undefined | void) | null = null;
let onopen: ((response: Response) => Promise<void>) | null = null;
let abortSignal: AbortSignal | null = null;
let passedHeaders: Record<string, string> | undefined;
let fetchEventSourceCallCount = 0;

vi.mock('@microsoft/fetch-event-source', () => ({
  fetchEventSource(
    _url: string,
    opts: {
      signal?: AbortSignal;
      headers?: Record<string, string>;
      onopen?: (response: Response) => Promise<void>;
      onmessage?: (msg: EventSourceMessage) => void;
      onerror?: (err: unknown) => number | null | undefined | void;
    },
  ) {
    fetchEventSourceCallCount++;
    onmessage = opts.onmessage ?? null;
    onerror = opts.onerror ?? null;
    onopen = opts.onopen ?? null;
    abortSignal = opts.signal ?? null;
    passedHeaders = opts.headers;
    return Promise.resolve();
  },
}));

import { sendEnvelope, connectSSE } from './sseClient';
import type { ConnStatus } from './sseClient';

beforeEach(() => {
  onmessage = null;
  onerror = null;
  onopen = null;
  abortSignal = null;
  passedHeaders = undefined;
  fetchEventSourceCallCount = 0;
  vi.useRealTimers();
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
    await sendEnvelope('http://localhost:8000', 'sid-1', env, 'Bearer elpat_test123');
    expect(mockFetch).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: 'Bearer elpat_test123',
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
    const result = connectSSE(
      'http://localhost:8000',
      'sid-1',
      vi.fn(),
      vi.fn(),
      'Bearer elpat_test123',
    );
    expect(passedHeaders).toEqual({ Authorization: 'Bearer elpat_test123' });
    result.cleanup();
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

  it('calls onStatus with connected on successful onopen', async () => {
    const onStatus = vi.fn();
    connectSSE('http://localhost:8000', 'sid-1', vi.fn(), onStatus);

    const response = new Response(null, {
      status: 200,
      headers: { 'content-type': 'text/event-stream' },
    });

    await onopen!(response);

    expect(onStatus).toHaveBeenCalledWith({ state: 'connected' });
  });

  it('calls onStatus with session_expired when onopen gets 404', async () => {
    const onStatus = vi.fn();
    connectSSE('http://localhost:8000', 'sid-1', vi.fn(), onStatus);

    const response = new Response(null, {
      status: 404,
      headers: { 'content-type': 'text/event-stream' },
    });

    // onopen throws SessionExpiredError; simulate library catching it
    let thrown: unknown;
    try {
      await onopen!(response);
    } catch (e) {
      thrown = e;
    }
    expect(thrown).toBeDefined();

    // library passes the thrown error to onerror
    expect(() => onerror!(thrown)).toThrow();

    expect(onStatus).toHaveBeenCalledWith({ state: 'session_expired' });
  });

  it('calls onStatus with reconnecting on generic onerror and schedules retry', () => {
    vi.useFakeTimers();
    const onStatus = vi.fn();
    connectSSE('http://localhost:8000', 'sid-1', vi.fn(), onStatus);

    // Simulate library calling onerror with a generic error (non-SessionExpired)
    expect(() => onerror!(new Error('network error'))).toThrow();

    expect(onStatus).toHaveBeenCalledWith(
      expect.objectContaining({ state: 'reconnecting' }),
    );
    const statusArg = onStatus.mock.calls.find(
      (c: ConnStatus[]) => c[0].state === 'reconnecting',
    )?.[0] as Extract<ConnStatus, { state: 'reconnecting' }>;
    expect(statusArg).toBeDefined();
    expect(statusArg.countdown).toBeGreaterThan(0);
  });

  it('retryNow clears timer and starts a new connection', () => {
    vi.useFakeTimers();
    const onStatus = vi.fn();
    const result = connectSSE('http://localhost:8000', 'sid-1', vi.fn(), onStatus);

    const prevCount = fetchEventSourceCallCount;

    // Trigger a retry
    expect(() => onerror!(new Error('network error'))).toThrow();
    expect(onStatus).toHaveBeenCalledWith(
      expect.objectContaining({ state: 'reconnecting' }),
    );

    // Before timer fires, call retryNow
    result.retryNow();

    // Should have started a new connection
    expect(fetchEventSourceCallCount).toBe(prevCount + 1);
  });

  it('cleanup aborts the connection', () => {
    const result = connectSSE('http://localhost:8000', 'sid-1', vi.fn(), vi.fn());
    expect(abortSignal!.aborted).toBe(false);
    result.cleanup();
    expect(abortSignal!.aborted).toBe(true);
  });

  it('skips invalid JSON in message data', () => {
    const onEvent = vi.fn();
    connectSSE('http://localhost:8000', 'sid-1', onEvent, vi.fn());
    onmessage!({ id: '', event: 'message', data: 'not json' });
    expect(onEvent).not.toHaveBeenCalled();
  });

  it('returns cleanup and retryNow methods', () => {
    const result = connectSSE('http://localhost:8000', 'sid-1', vi.fn(), vi.fn());
    expect(result).toHaveProperty('cleanup');
    expect(result).toHaveProperty('retryNow');
    expect(typeof result.cleanup).toBe('function');
    expect(typeof result.retryNow).toBe('function');
  });
});
