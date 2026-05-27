import BalanceCard from '@/components/BalanceCard';
import BotControls from '@/components/BotControls';
import StatsBar from '@/components/StatsBar';
import EquityChart from '@/components/EquityChart';
import PositionsList from '@/components/PositionsList';
import EventFeed from '@/components/EventFeed';
import PriceTickerBar from '@/components/PriceTickerBar';
import NewsFeed from '@/components/NewsFeed';

export default function DashboardPage() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Dashboard</h1>

      {/* Ticker giá real-time */}
      <PriceTickerBar />

      {/* Balance + Bot Controls */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <BalanceCard />
        <BotControls />
      </div>

      {/* PnL / win-rate stats */}
      <StatsBar />

      {/* Equity chart (2/3) + News Feed (1/3) */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2">
          <EquityChart />
        </div>
        <NewsFeed />
      </div>

      {/* Open positions + live event feed */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <PositionsList />
        <EventFeed />
      </div>
    </div>
  );
}
