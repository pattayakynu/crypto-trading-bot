'use client';
import { usePositions } from '@/lib/hooks';

interface Position {
  pair: string;
  side: string;
  market_type: string;
  entry_price: number;
  qty: number;
  usdt_value: number;
  stop_loss: number;
  take_profit: number;
  trailing_stop_active: boolean;
  highest_price: number | null;
  conviction_score: number | null;
}

export default function PositionsList() {
  const { data: positions, isLoading } = usePositions();

  if (isLoading) {
    return <div className="card h-40 animate-pulse" />;
  }

  return (
    <div className="card">
      <h2 className="text-sm text-gray-400 uppercase tracking-wide mb-4">Open Positions</h2>
      {!positions || (positions as Position[]).length === 0 ? (
        <p className="text-gray-500 text-sm">No open positions</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-gray-400 text-left border-b border-gray-700">
                <th className="pb-2 pr-4">Pair</th>
                <th className="pb-2 pr-4">Side</th>
                <th className="pb-2 pr-4">Entry</th>
                <th className="pb-2 pr-4">Value</th>
                <th className="pb-2 pr-4">SL</th>
                <th className="pb-2">TP</th>
              </tr>
            </thead>
            <tbody>
              {(positions as Position[]).map((p, i) => (
                <tr key={i} className="border-b border-gray-800 text-gray-200">
                  <td className="py-2 pr-4 font-medium">
                    {p.pair}
                    {p.trailing_stop_active && (
                      <span className="ml-1 text-xs text-yellow-400" title="Trailing stop active">▲</span>
                    )}
                  </td>
                  <td className="py-2 pr-4">
                    <span className={p.side === 'LONG' ? 'badge-green' : 'badge-red'}>
                      {p.side}
                    </span>
                  </td>
                  <td className="py-2 pr-4">${p.entry_price.toFixed(2)}</td>
                  <td className="py-2 pr-4">${p.usdt_value.toFixed(2)}</td>
                  <td className="py-2 pr-4 text-red-400">${p.stop_loss.toFixed(2)}</td>
                  <td className="py-2 text-green-400">${p.take_profit.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
