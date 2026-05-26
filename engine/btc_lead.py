import os

# BTC move thresholds to qualify as a lead signal
BTC_MOVE_STRONG = 2.0       # BTC > 2% in 1h = strong move
BTC_MOVE_MODERATE = 1.0     # BTC > 1% in 1h = moderate move
BTC_MOVE_WEAK = 0.3         # BTC > 0.3% = minor move (not a lead signal)

# Spot/futures volume ratio thresholds
# Ratio = spot_volume / (spot_volume + futures_volume)
# High ratio → move driven by real spot buyers → organic
# Low ratio → move driven by futures leverage → potentially fake
SPOT_RATIO_REAL = 0.55      # Spot > 55% = organic move
SPOT_RATIO_SUSPECT = 0.35   # Spot < 35% = leverage-driven, suspicious

# Altcoin correlation: if BTC pumps but alts don't follow, suspect fake
ALT_FOLLOW_MIN = 0.4        # Altcoin move should be at least 40% of BTC move

BTC_LEAD_MAX_SCORE = 20


class BtcLeadSignal:
    def __init__(self, client=None):
        self.client = client

    def score_btc_move(self, btc_change_pct: float, spot_futures_ratio: float) -> int:
        """
        BTC dẫn đầu = altcoin sẽ theo sau.
        Nhưng phải là spot-driven, không phải futures-driven (dễ bị reverse).
        """
        abs_move = abs(btc_change_pct)

        if abs_move < BTC_MOVE_WEAK:
            return 0    # Không đủ mạnh để trigger

        if spot_futures_ratio < SPOT_RATIO_SUSPECT:
            return 0    # Futures-driven: nguy hiểm, bỏ qua

        if abs_move >= BTC_MOVE_STRONG and spot_futures_ratio >= SPOT_RATIO_REAL:
            return 15   # Strong organic BTC move — high conviction

        if abs_move >= BTC_MOVE_MODERATE and spot_futures_ratio >= SPOT_RATIO_REAL:
            return 10   # Moderate organic move

        if abs_move >= BTC_MOVE_MODERATE and spot_futures_ratio >= SPOT_RATIO_SUSPECT:
            return 5    # Moderate but mixed spot/futures

        return 5        # Weak but real spot move

    def score_alt_correlation(self, btc_change_pct: float, alt_change_pct: float) -> int:
        """
        Altcoin phải follow BTC để xác nhận tín hiệu.
        Nếu BTC pump nhưng alt không follow → alt đang yếu relative to BTC.
        Nếu BTC pump + alt pump mạnh hơn → alt outperforming = very bullish.
        """
        if abs(btc_change_pct) < BTC_MOVE_WEAK:
            return 0    # BTC không move đủ để xét correlation

        # Tính ratio alt/btc move
        if btc_change_pct == 0:
            return 0

        follow_ratio = alt_change_pct / btc_change_pct

        if follow_ratio >= 1.5:
            return 5    # Alt outperforming BTC = very bullish
        if follow_ratio >= ALT_FOLLOW_MIN:
            return 3    # Alt following BTC = confirmed
        if follow_ratio < 0:
            return 0    # Alt diverging from BTC = suspicious
        return 1        # Alt lagging

    def total_score(
        self,
        btc_change_pct: float,
        spot_futures_ratio: float,
        alt_change_pct: float = 0.0
    ) -> int:
        btc_score = self.score_btc_move(btc_change_pct, spot_futures_ratio)

        # If BTC move rejected due to futures-driven pump, alt correlation is meaningless
        # (alts following a fake pump are also suspect)
        if btc_score == 0 and spot_futures_ratio < SPOT_RATIO_SUSPECT:
            return 0

        score = btc_score + self.score_alt_correlation(btc_change_pct, alt_change_pct)
        return min(BTC_LEAD_MAX_SCORE, score)

    def get_btc_1h_change(self) -> float:
        """Fetch BTC 1h price change from Binance."""
        if not self.client:
            return 0.0
        try:
            ticker = self.client.get_ticker(symbol="BTCUSDT")
            return float(ticker.get("priceChangePercent", 0))
        except Exception:
            return 0.0

    def get_spot_futures_ratio(self, symbol: str = "BTCUSDT") -> float:
        """
        Estimate spot/futures volume ratio.
        spot_vol / (spot_vol + futures_vol)
        """
        if not self.client:
            return 0.5  # Assume neutral when no client
        try:
            spot = self.client.get_ticker(symbol=symbol)
            futures = self.client.futures_ticker(symbol=symbol)
            spot_vol = float(spot.get("quoteVolume", 0))
            futures_vol = float(futures.get("quoteVolume", 0))
            total = spot_vol + futures_vol
            return spot_vol / total if total > 0 else 0.5
        except Exception:
            return 0.5
