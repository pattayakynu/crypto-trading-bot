'use client';
import { useBalance } from '@/lib/hooks';

export default function BalanceCard() {
  const { data, error, isLoading } = useBalance();

  if (isLoading) {
    return (
      <div className="card animate-pulse h-28">
        <div className="h-3 bg-gray-700 rounded w-24 mb-3" />
        <div className="h-8 bg-gray-700 rounded w-36" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="card">
        <h2 className="text-sm text-gray-400 uppercase tracking-wide mb-1">USDT Balance</h2>
        <p className="text-red-400 text-sm">Unavailable — check backend</p>
      </div>
    );
  }

  return (
    <div className="card">
      <h2 className="text-sm text-gray-400 uppercase tracking-wide mb-1">USDT Balance</h2>
      <div className="text-3xl font-bold text-white mt-1">
        ${(data.free as number).toFixed(2)}
      </div>
      <div className="text-sm text-gray-400 mt-2">
        Locked:&nbsp;
        <span className="text-gray-300">${(data.locked as number).toFixed(2)}</span>
      </div>
    </div>
  );
}
