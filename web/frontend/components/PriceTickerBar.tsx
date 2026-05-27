'use client';
import { useMarketPrices, type CoinPrice } from '@/lib/hooks';

export default function PriceTickerBar() {
  const { data, isLoading } = useMarketPrices();

  if (isLoading || !data) {
    return (
      <div className="bg-gray-900 border border-gray-800 rounded-lg px-4 py-2.5 flex gap-6 items-center">
        {['BTC', 'ETH', 'BNB', 'SOL', 'ADA'].map(s => (
          <div key={s} className="flex gap-2 items-center animate-pulse">
            <div className="h-3 w-8 bg-gray-700 rounded" />
            <div className="h-3 w-16 bg-gray-700 rounded" />
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg px-4 py-2.5 flex items-center flex-wrap gap-y-1">
      {data.map((coin: CoinPrice, i: number) => (
        <div key={coin.symbol} className="flex items-center">
          {i > 0 && <span className="text-gray-700 mx-3">|</span>}
          <span className="text-white font-semibold text-sm">{coin.symbol}</span>
          <span className="text-white text-sm ml-1.5">
            {coin.price != null
              ? `$${coin.price.toLocaleString('en-US', {
                  maximumFractionDigits: coin.price >= 1 ? 2 : 4,
                })}`
              : '—'}
          </span>
          {coin.change_pct_24h != null && (
            <span
              className={`text-xs ml-1.5 ${
                coin.change_pct_24h >= 0 ? 'text-green-400' : 'text-red-400'
              }`}
            >
              {coin.change_pct_24h >= 0 ? '▲' : '▼'}{' '}
              {Math.abs(coin.change_pct_24h).toFixed(2)}%
            </span>
          )}
        </div>
      ))}
      <div className="ml-auto flex items-center gap-1.5">
        <span className="h-1.5 w-1.5 rounded-full bg-green-400 animate-pulse" />
        <span className="text-gray-500 text-[10px]">10s</span>
      </div>
    </div>
  );
}
