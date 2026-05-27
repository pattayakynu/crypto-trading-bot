'use client';
import { useSignals, type CoinSignal, type SignalScan } from '@/lib/hooks';

// Layer display order (matches engine pipeline)
const LAYER_ORDER = ['whale', 'macro', 'fiat_flow', 'btc_lead', 'ta', 'social'];

function strengthBar(strength: string): string {
  if (strength === 'STRONG')   return 'bg-green-500';
  if (strength === 'MODERATE') return 'bg-yellow-500';
  if (strength === 'WEAK')     return 'bg-red-500';
  return 'bg-gray-700';
}

function ActionBadge({ action, confidence }: { action: string; confidence: string }) {
  if (action === 'BUY') {
    const cls = confidence === 'HIGH'
      ? 'text-green-300 border-green-400'
      : 'text-green-500 border-green-700';
    return (
      <span className={`text-[10px] border rounded px-1 py-0.5 leading-none ${cls}`}>
        MUA {confidence}
      </span>
    );
  }
  if (action === 'WATCH') {
    return (
      <span className="text-[10px] border rounded px-1 py-0.5 leading-none text-yellow-400 border-yellow-600">
        CHỜ
      </span>
    );
  }
  return (
    <span className="text-[10px] border rounded px-1 py-0.5 leading-none text-gray-500 border-gray-700">
      BỎ QUA
    </span>
  );
}

function timeAgo(iso: string | null): string {
  if (!iso) return '';
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1)  return 'vừa xong';
  if (mins < 60) return `${mins} ph trước`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24)  return `${hrs} giờ trước`;
  return `${Math.floor(hrs / 24)} ngày trước`;
}

function scoreColor(score: number): string {
  if (score >= 75) return 'text-green-400';
  if (score >= 55) return 'text-yellow-400';
  return 'text-gray-500';
}

function ScanCard({ scan, dim }: { scan: SignalScan; dim?: boolean }) {
  return (
    <div
      className={`border border-gray-800 rounded p-2.5 flex flex-col gap-2 ${dim ? 'opacity-40' : ''}`}
      data-testid="scan-card"
    >
      {/* Header: score + action + time */}
      <div className="flex items-center gap-2">
        <span className={`text-xl font-bold tabular-nums leading-none ${scoreColor(scan.total_score)}`}>
          {scan.total_score}
        </span>
        <div className="flex flex-col gap-0.5 min-w-0">
          <ActionBadge action={scan.action} confidence={scan.confidence} />
          <span className="text-gray-600 text-[9px]">{timeAgo(scan.scanned_at)}</span>
        </div>
      </div>

      {/* Layer bars */}
      <div className="space-y-1">
        {LAYER_ORDER.map(key => {
          const layer = scan.layers[key];
          if (!layer) return null;
          return (
            <div key={key} className="flex items-center gap-1.5">
              <span className="text-gray-500 text-[9px] w-14 flex-shrink-0 truncate">
                {layer.label}
              </span>
              <div className="flex-1 bg-gray-800 rounded-full h-1.5 overflow-hidden">
                <div
                  className={`h-full rounded-full ${strengthBar(layer.strength)}`}
                  style={{ width: `${layer.pct}%` }}
                />
              </div>
              <span className="text-gray-600 text-[9px] w-7 text-right flex-shrink-0 tabular-nums">
                {layer.score}/{layer.max}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function CoinRow({ coin }: { coin: CoinSignal }) {
  const sym = coin.pair.replace('USDT', '');

  if (coin.scans.length === 0) {
    return (
      <div className="border border-gray-800 rounded p-3 flex items-center justify-between opacity-30">
        <span className="text-xs font-mono font-bold text-gray-400">{sym}</span>
        <span className="text-gray-600 text-xs">Chưa scan</span>
      </div>
    );
  }

  const [latest, ...older] = coin.scans;
  const latest_score = latest.total_score;
  const trend = older.length > 0
    ? latest_score - older[0].total_score
    : null;

  return (
    <div className="border border-gray-800 rounded p-3">
      {/* Coin header */}
      <div className="flex items-center gap-2 mb-2">
        <span className="text-xs font-bold text-gray-200">{sym}</span>
        {trend !== null && (
          <span className={`text-[10px] ${trend > 0 ? 'text-green-500' : trend < 0 ? 'text-red-500' : 'text-gray-600'}`}>
            {trend > 0 ? `+${trend}` : trend}
          </span>
        )}
        <span className="text-gray-600 text-[10px] ml-auto">{coin.scans.length} scan</span>
      </div>

      {/* Scan cards: latest full, older faded */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
        <ScanCard scan={latest} />
        {older.map(s => (
          <ScanCard key={s.id} scan={s} dim />
        ))}
      </div>
    </div>
  );
}

export default function SignalInsight() {
  const { data, isLoading, error } = useSignals();

  // Loading skeleton
  if (isLoading) {
    return (
      <div className="card">
        <h2 className="text-sm text-gray-400 uppercase tracking-wide mb-4">Luồng suy nghĩ Bot</h2>
        <div className="animate-pulse space-y-3">
          {[1, 2, 3].map(i => (
            <div key={i} className="h-24 bg-gray-800 rounded" />
          ))}
        </div>
      </div>
    );
  }

  // Error state
  if (error || !data) {
    return (
      <div className="card">
        <h2 className="text-sm text-gray-400 uppercase tracking-wide mb-4">Luồng suy nghĩ Bot</h2>
        <p className="text-gray-500 text-sm">Không tải được tín hiệu.</p>
      </div>
    );
  }

  const active   = data.filter(c => c.scans.length > 0);
  const inactive = data.filter(c => c.scans.length === 0);

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-sm text-gray-400 uppercase tracking-wide">Luồng suy nghĩ Bot</h2>
        <span className="text-gray-600 text-xs">
          {active.length}/{data.length} coin · cập nhật mỗi 1 phút
        </span>
      </div>

      {active.length === 0 ? (
        <p className="text-gray-500 text-sm">
          Bot chưa scan lần nào. Dữ liệu xuất hiện sau lần scan đầu tiên (mỗi 5 phút).
        </p>
      ) : (
        <div className="space-y-3">
          {active.map(coin => (
            <CoinRow key={coin.pair} coin={coin} />
          ))}
          {inactive.length > 0 && (
            <div className="border border-gray-800 rounded px-3 py-2">
              <span className="text-gray-600 text-[10px]">
                Chưa scan: {inactive.map(c => c.pair.replace('USDT', '')).join(', ')}
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
