import { useEffect, useRef, useState } from 'react';
import { buildMarketWsUrl } from '../services/market';
import type { MarketStatusOut } from '../types/api';

type ConnectionState = 'connecting' | 'open' | 'closed';

interface MarketFeedState {
  connection: ConnectionState;
  data: MarketStatusOut | null;
}

const INITIAL_RECONNECT_DELAY_MS = 1000;
const MAX_RECONNECT_DELAY_MS = 15000;

/**
 * Subscribes to the /ws/market push feed (Phase 24/25). Unlike useAsync,
 * this never resolves once -- it keeps the connection open and updates
 * `data` on every server push, reconnecting with backoff if it drops.
 *
 * `WebSocketImpl` is injectable so tests can supply a fake WebSocket
 * instead of relying on a real connection (jsdom has no real network).
 */
export function useMarketFeed(WebSocketImpl: typeof WebSocket = WebSocket): MarketFeedState {
  const [state, setState] = useState<MarketFeedState>({ connection: 'connecting', data: null });
  const reconnectDelayRef = useRef(INITIAL_RECONNECT_DELAY_MS);

  useEffect(() => {
    let cancelled = false;
    let socket: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

    function connect() {
      if (cancelled) return;
      const token = localStorage.getItem('piq_token');
      if (!token) {
        setState({ connection: 'closed', data: null });
        return;
      }

      setState((s) => ({ ...s, connection: 'connecting' }));
      socket = new WebSocketImpl(buildMarketWsUrl(token));

      socket.onopen = () => {
        if (cancelled) return;
        reconnectDelayRef.current = INITIAL_RECONNECT_DELAY_MS;
        setState((s) => ({ ...s, connection: 'open' }));
      };

      socket.onmessage = (event: MessageEvent) => {
        if (cancelled) return;
        try {
          const parsed = JSON.parse(event.data) as MarketStatusOut;
          setState({ connection: 'open', data: parsed });
        } catch {
          // malformed push -- ignore this message, keep the connection
        }
      };

      socket.onclose = () => {
        if (cancelled) return;
        setState((s) => ({ ...s, connection: 'closed' }));
        reconnectTimer = setTimeout(connect, reconnectDelayRef.current);
        reconnectDelayRef.current = Math.min(reconnectDelayRef.current * 2, MAX_RECONNECT_DELAY_MS);
      };

      socket.onerror = () => {
        socket?.close();
      };
    }

    connect();

    return () => {
      cancelled = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      socket?.close();
    };
  }, [WebSocketImpl]);

  return state;
}
