'use client';
import { useTrades } from '@/lib/hooks';

interface Trade {
  id: number;
  pair: string;
  side: string;
  market_type: string;
  price: number;
  qty: number;
  usdt_value: number;
  pnl: number;
  conviction_score: number | null;
  created_at: string | null;
}

export default function TradeHistory({ pair }: { pair?: string }) {
  const { data: trades, isLoading } = useTrades(pair);

  if (isLoading) {
    return <div className="card h-64 animate-pulse" />;
  }

  return (
    <div className="card">
      <h2 className="text-sm text-gray-400 uppercase tracking-wide mb-4">
        Trade History {pair && <span className="text-blue-400 normal-case">— {pair}</span>}
      </h2>
      {!trades || (trades as Trade[]).length === 0 ? (
        <p className="text-gray-500 text-sm">No closed trades yet</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-gray-400 text-left border-b border-gray-700">
                <th className="pb-2 pr-4">Date</th>
                <th className="pb-2 pr-4">Pair</th>
                <th className="pb-2 pr-4">Side</th>
                <th className="pb-2 pr-4">Price</th>
                <th className="pb-2 pr-4">Value</th>
                <th className="pb-2 pr-4">PnL</th>
                <th className="pb-2">Score</th>
              </tr>
            </thead>
            <tbody>
              {(trades as Trade[]).map(t => (
                <tr key={t.id} className="border-b border-gray-800 text-gray-200">
                  <td className="py-2 pr-4 text-gray-400 text-xs">
                    {t.created_at
                      ? new Date(t.created_at).toLocaleDateString(undefined, {
                          month: 'short',
                          day: 'numeric',
                        })
                      : '—'}
                  </td>
                  <td className="py-2 pr-4 font-medium">{t.pair}</td>
                  <td className="py-2 pr-4">
                    <span className={t.side === 'BUY' ? 'badge-green' : 'badge-red'}>
                      {t.side}
                    </span>
                  </td>
                  <td className="py-2 pr-4">${t.price.toFixed(2)}</td>
                  <td className="py-2 pr-4">${t.usdt_value.toFixed(2)}</td>
                  <td
                    className={`py-2 pr-4 font-medium ${
                      t.pnl > 0 ? 'text-green-400' : 'text-red-400'
                    }`}
                  >
                    {t.pnl > 0 ? '+' : ''}${t.pnl.toFixed(2)}
                  </td>
                  <td className="py-2 text-gray-400">{t.conviction_score ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
