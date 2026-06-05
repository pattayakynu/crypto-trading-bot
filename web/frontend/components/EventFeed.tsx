'use client';
import { useWebSocket, type BotEvent } from '@/lib/hooks';

function formatEvent(e: BotEvent): { icon: string; text: string; color: string } {
  try {
    const d = JSON.parse(e.raw) as Record<string, unknown>;
    const type = (d.type as string) || e.type;

    if (type === 'trade_opened') {
      return {
        icon: '📈',
        color: 'text-green-400',
        text: `Mở lệnh ${d.side ?? 'LONG'} ${d.pair} — giá $${Number(d.entry_price ?? 0).toFixed(4)} | SL $${Number(d.stop_loss ?? 0).toFixed(4)} | TP $${Number(d.take_profit ?? 0).toFixed(4)} | Điểm ${d.conviction_score ?? '—'}/100`,
      };
    }

    if (type === 'trade_closed') {
      const pnl = Number(d.pnl ?? 0);
      const reasonMap: Record<string, string> = {
        take_profit: 'Chốt lời 🎯',
        stop_loss: 'Cắt lỗ 🛑',
        trailing_stop: 'Trailing stop 📎',
        manual: 'Thủ công ✋',
      };
      const reason = reasonMap[d.reason as string] ?? String(d.reason ?? '');
      return {
        icon: pnl >= 0 ? '✅' : '❌',
        color: pnl >= 0 ? 'text-green-400' : 'text-red-400',
        text: `Đóng lệnh ${d.pair} — ${reason} | PnL ${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)}`,
      };
    }

    if (type === 'signal') {
      const action = d.action as string;
      const actionMap: Record<string, string> = {
        BUY: '🟢 MUA',
        SKIP: '⏭ Bỏ qua',
        SKIP_FAKE_PUMP: '⚠️ Pump giả (futures)',
        SKIP_SPREAD: '💧 Spread rộng',
        SKIP_BEAR_REGIME: '🐻 BEAR regime',
        SKIP_CORRELATION: '🔗 Tương quan cao',
        SKIP_FUNDING_WINDOW: '⏰ Gần funding',
        SKIP_LLM_DISAGREEMENT: '🤖 AI không đồng thuận',
        SKIP_LLM_DISAGREEMENT_SHORT: '🤖 AI từ chối SHORT',
        SKIP_MAX_POSITIONS: '🔒 Đủ vị thế',
        SKIP_DRAWDOWN_GUARD: '🛡 Drawdown guard',
        SKIP_EQUITY_TOO_SMALL: '💸 Vốn quá nhỏ',
        BLACKLISTED: '🚫 Blacklist',
      };
      return {
        icon: '🔔',
        color: action === 'BUY' ? 'text-green-400' : 'text-yellow-400',
        text: `${d.pair} — ${actionMap[action] ?? action} | Điểm ${d.score ?? '—'}/100 (${d.confidence ?? ''})`,
      };
    }

    if (type === 'alert') {
      const levelMap: Record<string, string> = {
        INFO: 'ℹ️',
        WARNING: '⚠️',
        CRITICAL: '🚨',
      };
      return {
        icon: levelMap[d.level as string] ?? '📢',
        color: d.level === 'CRITICAL' ? 'text-red-400' : 'text-orange-400',
        text: String(d.message ?? ''),
      };
    }

    if (type === 'report') {
      return {
        icon: '📊',
        color: 'text-gray-400',
        text: 'Báo cáo thị trường đã gửi qua Telegram',
      };
    }
  } catch {
    // fallback
  }

  return { icon: '📌', color: 'text-gray-400', text: e.raw };
}

export default function EventFeed() {
  const events: BotEvent[] = useWebSocket(40);

  return (
    <div className="card flex flex-col">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm text-gray-400 uppercase tracking-wide">Sự kiện trực tiếp</h2>
        <span
          className={`h-2 w-2 rounded-full ${events.length > 0 ? 'bg-green-400 animate-pulse' : 'bg-gray-600'}`}
          title={events.length > 0 ? 'Đang kết nối' : 'Chưa có sự kiện'}
        />
      </div>

      {events.length === 0 ? (
        <p className="text-gray-500 text-sm">Đang chờ sự kiện…</p>
      ) : (
        <ul className="space-y-2 max-h-64 overflow-y-auto text-xs">
          {events.map(e => {
            const { icon, text, color } = formatEvent(e);
            return (
              <li key={e.id} className="flex gap-2 items-start border-b border-gray-800 pb-1">
                <span className="flex-shrink-0">{icon}</span>
                <div className="flex-1 min-w-0">
                  <span className={`${color} break-words`}>{text}</span>
                  <span className="block text-gray-600 text-[10px] mt-0.5">{e.timestamp}</span>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
