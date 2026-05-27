/**
 * Component render tests using React Testing Library.
 * SWR data is injected via mock; no real HTTP calls are made.
 */
import React from 'react';
import { render, screen } from '@testing-library/react';

// ── Mock SWR so we can inject arbitrary data per test ───────────────────────
jest.mock('swr', () => {
  const useSWR = jest.fn();
  useSWR.default = useSWR;
  return { __esModule: true, default: useSWR, useSWRConfig: () => ({ mutate: jest.fn() }) };
});

// ── Mock recharts to avoid canvas issues in jsdom ───────────────────────────
jest.mock('recharts', () => ({
  LineChart: ({ children }: { children: React.ReactNode }) => <div data-testid="line-chart">{children}</div>,
  Line: () => null,
  XAxis: () => null,
  YAxis: () => null,
  CartesianGrid: () => null,
  Tooltip: () => null,
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

// ── Mock WebSocket (EventFeed) ───────────────────────────────────────────────
jest.mock('../lib/hooks', () => ({
  useBalance: jest.fn(),
  usePositions: jest.fn(),
  usePerformance: jest.fn(),
  useTrades: jest.fn(),
  useBotStatus: jest.fn(),
  useWebSocket: jest.fn(() => []),
  useMarketPrices: jest.fn(),
  useMarketNews: jest.fn(),
}));

import useSWR from 'swr';
import * as hooks from '../lib/hooks';

import BalanceCard from '../components/BalanceCard';
import BotControls from '../components/BotControls';
import StatsBar from '../components/StatsBar';
import EquityChart from '../components/EquityChart';
import PositionsList from '../components/PositionsList';
import TradeHistory from '../components/TradeHistory';
import EventFeed from '../components/EventFeed';
import PriceTickerBar from '../components/PriceTickerBar';
import NewsFeed from '../components/NewsFeed';

const mockUseSWR = useSWR as jest.Mock;

// ────────────────────────────────────────────────────────────────────────────
describe('BalanceCard', () => {
  it('renders loading skeleton when isLoading', () => {
    (hooks.useBalance as jest.Mock).mockReturnValue({ data: null, isLoading: true, error: null });
    // BalanceCard uses useBalance internally
    const { container } = render(<BalanceCard />);
    expect(container.querySelector('.animate-pulse')).toBeTruthy();
  });

  it('renders balance data', () => {
    (hooks.useBalance as jest.Mock).mockReturnValue({
      data: { free: 87.5, locked: 5.0 },
      isLoading: false,
      error: null,
    });
    render(<BalanceCard />);
    expect(screen.getByText('$87.50')).toBeInTheDocument();
    expect(screen.getByText(/5\.00/)).toBeInTheDocument();
  });

  it('renders error state', () => {
    (hooks.useBalance as jest.Mock).mockReturnValue({ data: null, isLoading: false, error: new Error('fail') });
    render(<BalanceCard />);
    expect(screen.getByText(/unavailable/i)).toBeInTheDocument();
  });
});

// ────────────────────────────────────────────────────────────────────────────
describe('BotControls', () => {
  it('shows Running when status is running', () => {
    (hooks.useBotStatus as jest.Mock).mockReturnValue({ data: { status: 'running' }, isLoading: false });
    render(<BotControls />);
    expect(screen.getByText('Running')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Stop' })).toBeInTheDocument();
  });

  it('shows Stopped when status is stopped', () => {
    (hooks.useBotStatus as jest.Mock).mockReturnValue({ data: { status: 'stopped' }, isLoading: false });
    render(<BotControls />);
    expect(screen.getByText('Stopped')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Start' })).toBeInTheDocument();
  });
});

// ────────────────────────────────────────────────────────────────────────────
describe('StatsBar', () => {
  it('renders all four stat cards', () => {
    (hooks.usePerformance as jest.Mock).mockReturnValue({
      data: { total_pnl: 12.5, win_rate: 66.7, total_trades: 6, wins: 4, losses: 2 },
      isLoading: false,
    });
    render(<StatsBar />);
    expect(screen.getByText('+$12.50')).toBeInTheDocument();
    expect(screen.getByText('66.7%')).toBeInTheDocument();
    expect(screen.getByText('6')).toBeInTheDocument();
    expect(screen.getByText('4 / 2')).toBeInTheDocument();
  });

  it('shows placeholder when loading', () => {
    (hooks.usePerformance as jest.Mock).mockReturnValue({ data: null, isLoading: true });
    render(<StatsBar />);
    expect(screen.getAllByText('···').length).toBeGreaterThan(0);
  });
});

// ────────────────────────────────────────────────────────────────────────────
describe('EquityChart', () => {
  it('shows no-data message when equity_curve is empty', () => {
    (hooks.usePerformance as jest.Mock).mockReturnValue({
      data: { equity_curve: [] },
      isLoading: false,
    });
    render(<EquityChart />);
    expect(screen.getByText(/no equity data/i)).toBeInTheDocument();
  });

  it('renders chart when data is present', () => {
    (hooks.usePerformance as jest.Mock).mockReturnValue({
      data: {
        equity_curve: [
          { equity: 100, recorded_at: '2025-01-01T00:00:00' },
          { equity: 112, recorded_at: '2025-01-02T00:00:00' },
        ],
      },
      isLoading: false,
    });
    render(<EquityChart />);
    expect(screen.getByTestId('line-chart')).toBeInTheDocument();
  });
});

// ────────────────────────────────────────────────────────────────────────────
describe('PositionsList', () => {
  it('shows no-positions message when empty', () => {
    (hooks.usePositions as jest.Mock).mockReturnValue({ data: [], isLoading: false });
    render(<PositionsList />);
    expect(screen.getByText(/no open positions/i)).toBeInTheDocument();
  });

  it('renders position rows', () => {
    (hooks.usePositions as jest.Mock).mockReturnValue({
      data: [
        {
          pair: 'BTCUSDT', side: 'LONG', market_type: 'SPOT',
          entry_price: 65000, qty: 0.001, usdt_value: 65,
          stop_loss: 61750, take_profit: 69550,
          trailing_stop_active: false, highest_price: null, conviction_score: 72,
        },
      ],
      isLoading: false,
    });
    render(<PositionsList />);
    expect(screen.getByText('BTCUSDT')).toBeInTheDocument();
    expect(screen.getByText('LONG')).toBeInTheDocument();
  });
});

// ────────────────────────────────────────────────────────────────────────────
describe('TradeHistory', () => {
  it('shows no-trades message when empty', () => {
    (hooks.useTrades as jest.Mock).mockReturnValue({ data: [], isLoading: false });
    render(<TradeHistory />);
    expect(screen.getByText(/no closed trades/i)).toBeInTheDocument();
  });

  it('renders trade rows with PnL colouring', () => {
    (hooks.useTrades as jest.Mock).mockReturnValue({
      data: [
        {
          id: 1, pair: 'ETHUSDT', side: 'BUY', market_type: 'SPOT',
          price: 3500, qty: 0.01, usdt_value: 35, pnl: 2.5,
          conviction_score: 68, created_at: '2025-03-01T00:00:00',
        },
      ],
      isLoading: false,
    });
    render(<TradeHistory />);
    expect(screen.getByText('ETHUSDT')).toBeInTheDocument();
    expect(screen.getByText('+$2.50')).toBeInTheDocument();
  });
});

// ────────────────────────────────────────────────────────────────────────────
describe('EventFeed', () => {
  it('shows waiting message when no events', () => {
    (hooks.useWebSocket as jest.Mock).mockReturnValue([]);
    render(<EventFeed />);
    expect(screen.getByText(/waiting for events/i)).toBeInTheDocument();
  });

  it('renders event entries', () => {
    (hooks.useWebSocket as jest.Mock).mockReturnValue([
      { id: 0, type: 'trade.opened', raw: '{"event":"trade.opened"}', timestamp: '12:00:00' },
    ]);
    render(<EventFeed />);
    expect(screen.getByText('[trade.opened]')).toBeInTheDocument();
  });
});

// ────────────────────────────────────────────────────────────────────────────
describe('PriceTickerBar', () => {
  it('renders skeleton when loading', () => {
    (hooks.useMarketPrices as jest.Mock).mockReturnValue({ data: null, isLoading: true });
    const { container } = render(<PriceTickerBar />);
    expect(container.querySelector('.animate-pulse')).toBeTruthy();
  });

  it('renders coin prices with green color for positive change', () => {
    (hooks.useMarketPrices as jest.Mock).mockReturnValue({
      data: [
        { symbol: 'BTC', price: 67420, change_pct_24h: 1.24 },
        { symbol: 'ETH', price: 3210,  change_pct_24h: -0.87 },
      ],
      isLoading: false,
    });
    render(<PriceTickerBar />);
    expect(screen.getByText('BTC')).toBeInTheDocument();
    expect(screen.getByText('ETH')).toBeInTheDocument();
    expect(screen.getByText(/1\.24%/)).toBeInTheDocument();
    expect(screen.getByText(/0\.87%/)).toBeInTheDocument();
  });

  it('renders em-dash when price is null', () => {
    (hooks.useMarketPrices as jest.Mock).mockReturnValue({
      data: [{ symbol: 'BTC', price: null, change_pct_24h: null }],
      isLoading: false,
    });
    render(<PriceTickerBar />);
    expect(screen.getByText('—')).toBeInTheDocument();
  });
});
