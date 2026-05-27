'use client';
import { useState } from 'react';
import { useMarketNews, type NewsItem } from '@/lib/hooks';

type Tab = 'all' | 'crypto' | 'macro';

function timeAgo(published: string): string {
  try {
    const diff = Math.floor((Date.now() - new Date(published).getTime()) / 1000);
    if (diff < 60) return `${diff}s trước`;
    if (diff < 3600) return `${Math.floor(diff / 60)} phút trước`;
    if (diff < 86400) return `${Math.floor(diff / 3600)} giờ trước`;
    return `${Math.floor(diff / 86400)} ngày trước`;
  } catch {
    return '';
  }
}

function newsIcon(item: NewsItem): string {
  if (item.importance === 'high') return '🚨';
  if (item.category === 'crypto') return '📈';
  return '📉';
}

export default function NewsFeed() {
  const { data, isLoading, error } = useMarketNews();
  const [tab, setTab] = useState<Tab>('all');

  const filtered = (data ?? []).filter(
    item => tab === 'all' || item.category === tab
  );

  return (
    <div className="card flex flex-col">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm text-gray-400 uppercase tracking-wide">Tin tức</h2>
        <div className="flex gap-1">
          {(['all', 'crypto', 'macro'] as Tab[]).map(t => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`text-[10px] px-2 py-0.5 rounded transition-colors ${
                tab === t
                  ? 'bg-blue-900 text-blue-300'
                  : 'bg-gray-800 text-gray-500 hover:text-gray-300'
              }`}
            >
              {t === 'all' ? 'Tất cả' : t === 'crypto' ? 'Crypto' : 'Macro'}
            </button>
          ))}
        </div>
      </div>

      {isLoading && (
        <div className="space-y-3">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="animate-pulse flex gap-2">
              <div className="h-3 w-3 bg-gray-700 rounded flex-shrink-0 mt-0.5" />
              <div className="flex-1 space-y-1">
                <div className="h-3 bg-gray-700 rounded w-full" />
                <div className="h-2 bg-gray-800 rounded w-1/3" />
              </div>
            </div>
          ))}
        </div>
      )}

      {!isLoading && error && !data && (
        <p className="text-gray-500 text-sm">Không tải được tin tức.</p>
      )}

      {!isLoading && !error && filtered.length === 0 && (
        <p className="text-gray-500 text-sm">Không có tin tức.</p>
      )}

      {!isLoading && filtered.length > 0 && (
        <ul className="space-y-0 overflow-y-auto max-h-72 text-xs">
          {filtered.map((item, i) => (
            <li key={i} className="border-b border-gray-800 py-2 last:border-0">
              <a
                href={item.url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex gap-2 items-start hover:bg-gray-800/40 rounded px-1 -mx-1 transition-colors"
              >
                <span className="flex-shrink-0 mt-0.5">{newsIcon(item)}</span>
                <div className="flex-1 min-w-0">
                  <span
                    className={`break-words leading-snug ${
                      item.importance === 'high' ? 'text-red-300' : 'text-gray-200'
                    }`}
                  >
                    {item.title}
                  </span>
                  <span className="block text-gray-600 text-[10px] mt-0.5">
                    {item.source} · {timeAgo(item.published_at)}
                  </span>
                </div>
              </a>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
