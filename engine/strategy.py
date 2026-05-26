import pandas as pd
import pandas_ta as ta

# RSI thresholds
RSI_OVERSOLD = 35       # RSI < 35 = oversold = potential buy
RSI_NEUTRAL_LOW = 45    # RSI 35-45 = leaning oversold
RSI_NEUTRAL_HIGH = 60   # RSI 45-60 = neutral
RSI_OVERBOUGHT = 70     # RSI > 70 = overbought = risky to buy

# MACD signal
MACD_BULLISH_HIST_MIN = 0   # Histogram positive = momentum up

# Bollinger Band
BB_OVERSOLD_PCT = 0.1       # Price within 10% of lower band = oversold zone
BB_OVERBOUGHT_PCT = 0.9     # Price within 10% of upper band = overbought zone

# EMA trend
EMA_FAST = 21
EMA_SLOW = 55

TA_MAX_SCORE = 10


class TaStrategy:
    def score_rsi(self, rsi: float) -> int:
        """RSI oversold = buying opportunity. Overbought = late, risky."""
        if rsi < RSI_OVERSOLD:
            return 4    # Oversold — strong buy signal
        if rsi < RSI_NEUTRAL_LOW:
            return 3    # Leaning oversold
        if rsi < RSI_NEUTRAL_HIGH:
            return 2    # Neutral territory
        if rsi < RSI_OVERBOUGHT:
            return 1    # Getting hot
        return 0        # Overbought — skip

    def score_macd(self, macd_line: float, signal_line: float, histogram: float) -> int:
        """
        MACD bullish cross + positive histogram = momentum building.
        """
        bullish_cross = macd_line > signal_line
        hist_positive = histogram > MACD_BULLISH_HIST_MIN
        hist_growing = histogram > 0  # Simplified: check if momentum is positive

        if bullish_cross and hist_positive:
            return 3    # Classic bullish signal
        if bullish_cross and not hist_positive:
            return 1    # Cross happened but histogram still catching up
        return 0        # Bearish MACD

    def score_bb_position(self, price: float, bb_lower: float, bb_upper: float) -> int:
        """
        Price near lower band = oversold zone.
        Price near upper band = overbought zone.
        """
        if bb_upper == bb_lower:
            return 1    # Flat bands — neutral
        bb_range = bb_upper - bb_lower
        position = (price - bb_lower) / bb_range  # 0 = at lower, 1 = at upper

        if position <= BB_OVERSOLD_PCT:
            return 3    # At/below lower band = buy zone
        if position <= 0.35:
            return 2    # Lower half — mild bullish
        if position <= BB_OVERBOUGHT_PCT:
            return 1    # Neutral to slightly stretched
        return 0        # At/above upper band = overbought

    def score_ema_trend(self, ema_fast: float, ema_slow: float) -> int:
        """
        Fast EMA above slow EMA = uptrend. Buy on dips.
        Fast EMA below slow EMA = downtrend. Avoid longs.
        """
        if ema_fast > ema_slow * 1.02:
            return 0    # Chased too far above — late entry
        if ema_fast > ema_slow:
            return 3    # Uptrend — healthy
        if ema_fast >= ema_slow * 0.99:
            return 2    # Just crossed below — possible reversal
        return 0        # Downtrend confirmed — avoid long

    def calculate_indicators(self, df: pd.DataFrame) -> dict:
        """
        Calculate all TA indicators from OHLCV dataframe.
        df: columns = ['open', 'high', 'low', 'close', 'volume']
        Returns dict with latest values for RSI, MACD, BB, EMA.
        """
        if len(df) < 60:
            return {}

        close = df["close"]
        high = df["high"]
        low = df["low"]

        # RSI(14)
        rsi_series = ta.rsi(close, length=14)
        rsi = float(rsi_series.iloc[-1]) if rsi_series is not None else 50.0

        # MACD(12,26,9)
        macd_df = ta.macd(close, fast=12, slow=26, signal=9)
        if macd_df is not None and not macd_df.empty:
            macd_line = float(macd_df["MACD_12_26_9"].iloc[-1])
            signal_line = float(macd_df["MACDs_12_26_9"].iloc[-1])
            histogram = float(macd_df["MACDh_12_26_9"].iloc[-1])
        else:
            macd_line = signal_line = histogram = 0.0

        # Bollinger Bands(20, 2)
        bb_df = ta.bbands(close, length=20, std=2)
        if bb_df is not None and not bb_df.empty:
            # pandas_ta column name format: BBL_20_2.0_2.0 (length_std_std)
            bb_lower_col = [c for c in bb_df.columns if c.startswith("BBL_")][0]
            bb_upper_col = [c for c in bb_df.columns if c.startswith("BBU_")][0]
            bb_lower = float(bb_df[bb_lower_col].iloc[-1])
            bb_upper = float(bb_df[bb_upper_col].iloc[-1])
        else:
            bb_lower = bb_upper = float(close.iloc[-1])

        # EMA(21) and EMA(55)
        ema_fast = float(ta.ema(close, length=EMA_FAST).iloc[-1])
        ema_slow = float(ta.ema(close, length=EMA_SLOW).iloc[-1])

        return {
            "rsi": rsi,
            "macd_line": macd_line,
            "signal_line": signal_line,
            "histogram": histogram,
            "bb_lower": bb_lower,
            "bb_upper": bb_upper,
            "ema_fast": ema_fast,
            "ema_slow": ema_slow,
            "current_price": float(close.iloc[-1]),
        }

    def total_score(
        self,
        rsi: float,
        macd_line: float,
        signal_line: float,
        histogram: float,
        price: float,
        bb_lower: float,
        bb_upper: float,
        ema_fast: float,
        ema_slow: float
    ) -> int:
        score = (
            self.score_rsi(rsi) +
            self.score_macd(macd_line, signal_line, histogram) +
            self.score_bb_position(price, bb_lower, bb_upper) +
            self.score_ema_trend(ema_fast, ema_slow)
        )
        return min(TA_MAX_SCORE, score)

    def get_score_from_df(self, df: pd.DataFrame) -> int:
        """Full pipeline: dataframe → indicators → score."""
        indicators = self.calculate_indicators(df)
        if not indicators:
            return 0
        return self.total_score(
            rsi=indicators["rsi"],
            macd_line=indicators["macd_line"],
            signal_line=indicators["signal_line"],
            histogram=indicators["histogram"],
            price=indicators["current_price"],
            bb_lower=indicators["bb_lower"],
            bb_upper=indicators["bb_upper"],
            ema_fast=indicators["ema_fast"],
            ema_slow=indicators["ema_slow"],
        )
