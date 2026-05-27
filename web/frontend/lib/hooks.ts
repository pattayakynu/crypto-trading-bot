'use client';
import useSWR from 'swr';
import { fetcher, wsUrl } from './api';
import { useEffect, useRef, useState } from 'react';

export function useBalance() {
  return useSWR('/api/balance', fetcher, { refreshInterval: 15_000 });
}

export function usePositions() {
  return useSWR('/api/positions', fetcher, { refreshInterval: 15_000 });
}

export function usePerformance() {
  return useSWR('/api/performance', fetcher, { refreshInterval: 30_000 });
}

export function useTrades(pair?: string) {
  const key = pair ? `/api/trades?pair=${encodeURIComponent(pair)}` : '/api/trades';
  return useSWR(key, fetcher, { refreshInterval: 30_000 });
}

export function useBotStatus() {
  return useSWR('/api/bot/status', fetcher, { refreshInterval: 5_000 });
}

export interface BotEvent {
  id: number;
  type: string;
  raw: string;
  timestamp: string;
}

export function useWebSocket(maxEvents = 50): BotEvent[] {
  const [events, setEvents] = useState<BotEvent[]>([]);
  const wsRef = useRef<WebSocket | null>(null);
  const counterRef = useRef(0);

  useEffect(() => {
    const url = wsUrl();

    function connect() {
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onmessage = (e: MessageEvent) => {
        try {
          const data = JSON.parse(e.data as string) as Record<string, unknown>;
          const event: BotEvent = {
            id: counterRef.current++,
            type: (data.event as string) || (data.type as string) || 'unknown',
            raw: e.data as string,
            timestamp: new Date().toLocaleTimeString(),
          };
          setEvents(prev => [event, ...prev].slice(0, maxEvents));
        } catch {
          // ignore malformed messages
        }
      };

      ws.onclose = () => {
        // auto-reconnect after 3 s
        setTimeout(connect, 3_000);
      };

      ws.onerror = () => {
        ws.close();
      };
    }

    connect();

    return () => {
      wsRef.current?.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return events;
}

// ── Market Prices ─────────────────────────────────────────────────────────────

export interface CoinPrice {
  symbol: string;
  price: number | null;
  change_pct_24h: number | null;
}

export function useMarketPrices() {
  return useSWR<CoinPrice[]>('/api/market/prices', fetcher, { refreshInterval: 10_000 });
}

// ── Market News ───────────────────────────────────────────────────────────────

export interface NewsItem {
  title: string;
  url: string;
  source: string;
  published_at: string;
  category: 'crypto' | 'macro';
  importance: 'normal' | 'high';
}

export function useMarketNews() {
  return useSWR<NewsItem[]>('/api/market/news', fetcher, { refreshInterval: 300_000 });
}

// ── Signal Insights ───────────────────────────────────────────────────────────

export interface LayerInfo {
  score: number;
  max: number;
  pct: number;
  strength: 'STRONG' | 'MODERATE' | 'WEAK' | 'NONE';
  label: string;
}

export interface SignalScan {
  id: number;
  scanned_at: string | null;
  total_score: number;
  action: string;
  confidence: 'HIGH' | 'MEDIUM' | 'LOW';
  layers: Record<string, LayerInfo>;
}

export interface CoinSignal {
  pair: string;
  scans: SignalScan[];
}

export function useSignals() {
  return useSWR<CoinSignal[]>('/api/signals/latest', fetcher, { refreshInterval: 60_000 });
}
