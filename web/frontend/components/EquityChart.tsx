'use client';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts';
import { usePerformance } from '@/lib/hooks';

interface EquityPoint {
  equity: number;
  recorded_at: string;
}

interface ChartDatum {
  equity: number;
  time: string;
}

export default function EquityChart() {
  const { data, isLoading } = usePerformance();

  if (isLoading) {
    return <div className="card h-72 animate-pulse" />;
  }

  const chartData: ChartDatum[] = ((data?.equity_curve ?? []) as EquityPoint[]).map(p => ({
    equity: p.equity,
    time: new Date(p.recorded_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }),
  }));

  if (chartData.length === 0) {
    return (
      <div className="card h-72 flex items-center justify-center text-gray-500 text-sm">
        No equity data yet — trades will appear here
      </div>
    );
  }

  return (
    <div className="card">
      <h2 className="text-sm text-gray-400 uppercase tracking-wide mb-4">Equity Curve</h2>
      <ResponsiveContainer width="100%" height={240}>
        <LineChart data={chartData} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
          <XAxis
            dataKey="time"
            tick={{ fill: '#9ca3af', fontSize: 11 }}
            tickLine={false}
            axisLine={false}
          />
          <YAxis
            tick={{ fill: '#9ca3af', fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            domain={['auto', 'auto']}
            tickFormatter={(v: number) => `$${v.toFixed(0)}`}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: '#1f2937',
              border: '1px solid #374151',
              borderRadius: 8,
              fontSize: 12,
            }}
            labelStyle={{ color: '#d1d5db' }}
            formatter={(v: number) => [`$${v.toFixed(2)}`, 'Equity']}
          />
          <Line
            type="monotone"
            dataKey="equity"
            stroke="#3b82f6"
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4, fill: '#3b82f6' }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
