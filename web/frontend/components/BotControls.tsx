'use client';
import { useState } from 'react';
import { useSWRConfig } from 'swr';
import { useBotStatus } from '@/lib/hooks';
import { postCommand } from '@/lib/api';

export default function BotControls() {
  const { data, isLoading } = useBotStatus();
  const { mutate } = useSWRConfig();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const running = data?.status === 'running';

  const toggle = async () => {
    setBusy(true);
    setError('');
    try {
      await postCommand(running ? '/api/bot/stop' : '/api/bot/start');
      await mutate('/api/bot/status');
    } catch (e: any) {
      setError(e.message || 'Failed to connect to backend');
    } finally {
      setBusy(false);
    }
  };

  const statusColor = isLoading
    ? 'bg-gray-500'
    : running
    ? 'bg-green-400 animate-pulse'
    : 'bg-red-400';

  const statusText = isLoading ? 'Checking…' : running ? 'Running' : 'Stopped';

  return (
    <div className="card">
      <h2 className="text-sm text-gray-400 uppercase tracking-wide mb-3">Bot Status</h2>
      <div className="flex items-center gap-3">
        <span className={`h-3 w-3 rounded-full flex-shrink-0 ${statusColor}`} />
        <span className="text-white font-medium">{statusText}</span>
        <button
          onClick={toggle}
          disabled={isLoading || busy}
          className={`ml-auto px-4 py-1.5 rounded text-sm font-medium transition-colors
            ${running
              ? 'bg-red-600 hover:bg-red-700 text-white'
              : 'bg-green-600 hover:bg-green-700 text-white'}
            disabled:opacity-50 disabled:cursor-not-allowed`}
        >
          {busy ? '…' : running ? 'Stop' : 'Start'}
        </button>
      </div>
      {error && (
        <p className="mt-2 text-xs text-red-400">{error}</p>
      )}
    </div>
  );
}
