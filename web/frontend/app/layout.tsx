import type { Metadata } from 'next';
import Link from 'next/link';
import './globals.css';

export const metadata: Metadata = {
  title: 'Crypto Trading Bot',
  description: 'Real-time dashboard for the crypto trading bot',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-gray-950 text-white min-h-screen">
        <nav className="border-b border-gray-800 px-6 py-4">
          <div className="max-w-7xl mx-auto flex items-center gap-6">
            <span className="text-white font-bold text-lg tracking-tight">
              ⚡ TradingBot
            </span>
            <Link href="/" className="text-sm text-gray-400 hover:text-white transition">
              Dashboard
            </Link>
            <Link href="/trades" className="text-sm text-gray-400 hover:text-white transition">
              Trades
            </Link>
          </div>
        </nav>
        <main className="max-w-7xl mx-auto px-6 py-8">{children}</main>
      </body>
    </html>
  );
}
