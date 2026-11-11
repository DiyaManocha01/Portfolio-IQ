import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useMarketFeed } from './useMarketFeed';

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  url: string;
  onopen: (() => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }

  close() {
    this.closed = true;
    this.onclose?.();
  }

  emitOpen() {
    this.onopen?.();
  }

  emitMessage(data: unknown) {
    this.onmessage?.({ data: JSON.stringify(data) } as MessageEvent);
  }
}

beforeEach(() => {
  FakeWebSocket.instances = [];
  localStorage.setItem('piq_token', 'test-token');
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  localStorage.clear();
});

describe('useMarketFeed', () => {
  it('starts in connecting state and carries the token in the URL', () => {
    const { result } = renderHook(() => useMarketFeed(FakeWebSocket as unknown as typeof WebSocket));
    expect(result.current.connection).toBe('connecting');
    expect(FakeWebSocket.instances[0].url).toContain('token=test-token');
  });

  it('transitions to closed immediately when there is no token', () => {
    localStorage.removeItem('piq_token');
    const { result } = renderHook(() => useMarketFeed(FakeWebSocket as unknown as typeof WebSocket));
    expect(result.current.connection).toBe('closed');
    expect(FakeWebSocket.instances).toHaveLength(0);
  });

  it('moves to open and stores pushed data on message', () => {
    const { result } = renderHook(() => useMarketFeed(FakeWebSocket as unknown as typeof WebSocket));
    const socket = FakeWebSocket.instances[0];

    act(() => socket.emitOpen());
    expect(result.current.connection).toBe('open');

    act(() =>
      socket.emitMessage({
        market_status: 'OPEN',
        feed_status: 'CONNECTED',
        server_time: '2026-11-11T10:00:00Z',
        ticks: [],
      })
    );
    expect(result.current.data?.market_status).toBe('OPEN');
  });

  it('reconnects with a new socket after the server closes the connection', async () => {
    renderHook(() => useMarketFeed(FakeWebSocket as unknown as typeof WebSocket));
    const first = FakeWebSocket.instances[0];

    act(() => first.close());
    expect(FakeWebSocket.instances).toHaveLength(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });

    expect(FakeWebSocket.instances).toHaveLength(2);
  });

  it('closes the socket on unmount without reconnecting', () => {
    const { unmount } = renderHook(() => useMarketFeed(FakeWebSocket as unknown as typeof WebSocket));
    const socket = FakeWebSocket.instances[0];

    unmount();

    expect(socket.closed).toBe(true);
  });
});
