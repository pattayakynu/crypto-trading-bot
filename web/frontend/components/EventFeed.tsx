'use client';
import { useWebSocket, type BotEvent } from '@/lib/hooks';

const EVENT_COLORS: Record<string, string> = {
  'trade.opened': 'text-green-400',
  'trade.closed': 'text-blue-400',
  signal: 'text-yellow-400',
  alert: 'text-red-400',
  report: 'text-gray-400',
};

export default function EventFeed() {
  const events: BotEvent[] = useWebSocket(40);

  return (
    <div className="card flex flex-col">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm text-gray-400 uppercase tracking-wide">Live Events</h2>
        <span
          className={`h-2 w-2 rounded-full ${events.length > 0 ? 'bg-green-400 animate-pulse' : 'bg-gray-600'}`}
          title={events.length > 0 ? 'Connected' : 'No events yet'}
        />
      </div>

      {events.length === 0 ? (
        <p className="text-gray-500 text-sm">Waiting for events…</p>
      ) : (
        <ul className="space-y-1 max-h-64 overflow-y-auto text-xs font-mono">
          {events.map(e => (
            <li key={e.id} className="flex gap-2 items-start">
              <span className="text-gray-600 flex-shrink-0">{e.timestamp}</span>
              <span className={`flex-shrink-0 ${EVENT_COLORS[e.type] ?? 'text-gray-300'}`}>
                [{e.type}]
              </span>
              <span className="text-gray-300 break-all">{e.raw}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
