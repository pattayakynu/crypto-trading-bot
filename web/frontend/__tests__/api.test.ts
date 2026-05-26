/**
 * Tests for lib/api.ts — fetcher, postCommand, wsUrl helpers.
 * All fetch calls are mocked so no network is needed.
 */

// We need to set env vars BEFORE importing the module
process.env.NEXT_PUBLIC_API_URL = 'http://test-backend:8000';
process.env.NEXT_PUBLIC_API_KEY = 'test-key-123';

// Force module to re-load with the env vars above
jest.resetModules();

import { fetcher, postCommand, wsUrl } from '../lib/api';

// Mock global fetch
global.fetch = jest.fn();

function mockFetch(body: unknown, ok = true, status = 200) {
  (global.fetch as jest.Mock).mockResolvedValueOnce({
    ok,
    status,
    json: async () => body,
  });
}

beforeEach(() => {
  (global.fetch as jest.Mock).mockClear();
});

describe('fetcher', () => {
  it('GETs the correct URL with API key header', async () => {
    mockFetch({ asset: 'USDT', free: 87.5 });
    const data = await fetcher('/api/balance');
    expect(data).toEqual({ asset: 'USDT', free: 87.5 });
    expect(global.fetch).toHaveBeenCalledWith(
      'http://test-backend:8000/api/balance',
      expect.objectContaining({
        headers: expect.objectContaining({ 'X-API-Key': 'test-key-123' }),
      }),
    );
  });

  it('throws on non-OK response', async () => {
    mockFetch({}, false, 401);
    await expect(fetcher('/api/balance')).rejects.toThrow('HTTP 401');
  });
});

describe('postCommand', () => {
  it('POSTs to the correct URL', async () => {
    mockFetch({ ok: true, action: 'start' });
    const data = await postCommand('/api/bot/start');
    expect(data).toEqual({ ok: true, action: 'start' });
    const [url, opts] = (global.fetch as jest.Mock).mock.calls[0] as [
      string,
      RequestInit,
    ];
    expect(url).toBe('http://test-backend:8000/api/bot/start');
    expect(opts.method).toBe('POST');
  });

  it('throws on non-OK response', async () => {
    mockFetch({}, false, 500);
    await expect(postCommand('/api/bot/start')).rejects.toThrow('HTTP 500');
  });
});

describe('wsUrl', () => {
  it('converts http to ws and appends ws events path', () => {
    const url = wsUrl();
    expect(url).toBe('ws://test-backend:8000/api/ws/events');
  });
});
