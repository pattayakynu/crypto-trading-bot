'use client';
import { usePerformance } from '@/lib/hooks';

interface Stat {
  label: string;
  value: string;
  color: string;
}

export default function StatsBar() {
  const { data, isLoading } = usePerformance();

  const pnl: number = data?.total_pnl ?? 0;

  const stats: Stat[] = [
    {
      label: 'Total PnL',
      value: data ? `${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)}` : '—',
      color: data ? (pnl >= 0 ? 'text-green-400' : 'text-red-400') : 'text-gray-300',
    },
    {
      label: 'Win Rate',
      value: data ? `${(data.win_rate as number).toFixed(1)}%` : '—',
      color: 'text-blue-400',
    },
    {
      label: 'Total Trades',
      value: data ? String(data.total_trades) : '—',
      color: 'text-white',
    },
    {
      label: 'Wins / Losses',
      value: data ? `${data.wins} / ${data.losses}` : '—',
      color: 'text-gray-300',
    },
  ];

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      {stats.map(s => (
        <div key={s.label} className="card">
          <div className="text-xs text-gray-400 uppercase tracking-wide">{s.label}</div>
          <div
            className={`text-2xl font-bold mt-1 ${
              isLoading ? 'text-gray-600 animate-pulse' : s.color
            }`}
          >
            {isLoading ? '···' : s.value}
          </div>
        </div>
      ))}
    </div>
  );
}
