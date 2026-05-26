'use client';
import { useState } from 'react';
import TradeHistory from '@/components/TradeHistory';

export default function TradesPage() {
  const [inputPair, setInputPair] = useState('');
  const [activePair, setActivePair] = useState<string | undefined>(undefined);

  const applyFilter = () => setActivePair(inputPair.trim().toUpperCase() || undefined);
  const clearFilter = () => { setInputPair(''); setActivePair(undefined); };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center gap-3">
        <h1 className="text-2xl font-bold flex-1">Trade History</h1>
        <div className="flex gap-2">
          <input
            type="text"
            placeholder="Filter by pair (e.g. BTCUSDT)"
            value={inputPair}
            onChange={e => setInputPair(e.target.value.toUpperCase())}
            onKeyDown={e => e.key === 'Enter' && applyFilter()}
            className="bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-sm
                       text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 w-56"
          />
          <button
            onClick={applyFilter}
            className="px-4 py-1.5 bg-blue-600 hover:bg-blue-700 rounded text-sm font-medium transition"
          >
            Filter
          </button>
          {activePair && (
            <button
              onClick={clearFilter}
              className="px-4 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-sm transition"
            >
              Clear
            </button>
          )}
        </div>
      </div>

      <TradeHistory pair={activePair} />
    </div>
  );
}
