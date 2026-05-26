from enum import Enum

FAKE_PUMP_BTC_THRESHOLD = 1.5     # BTC move % để coi là pump
FAKE_PUMP_RATIO_THRESHOLD = 0.45  # spot/futures ratio min để coi là real
STOP_HUNT_DIP_THRESHOLD = 0.003   # dip > 0.3% below support
STOP_HUNT_MAX_MINUTES = 5         # phục hồi trong vòng 5 phút
WASH_TRADE_VOLUME_MIN = 3.0       # volume ratio tối thiểu để nghi ngờ
WASH_TRADE_COUNT_MAX = 1.8        # trade count ratio tối đa để confirm
SPOOF_WALL_MIN_USDT = 500_000     # kích thước wall tối thiểu
SPOOF_MAX_AGE_SECONDS = 30        # wall biến mất trong vòng 30s


class ManipulationResult(Enum):
    CLEAN = "CLEAN"
    FAKE_PUMP = "FAKE_PUMP"
    STOP_HUNT_REVERSAL = "STOP_HUNT_REVERSAL"
    WASH_TRADE = "WASH_TRADE"
    SPOOF_ORDER = "SPOOF_ORDER"


class ManipulationFilter:
    def check_btc_pump(self, btc_change_pct: float, spot_futures_ratio: float) -> ManipulationResult:
        """Phát hiện BTC pump giả do futures leverage cascade."""
        if abs(btc_change_pct) < FAKE_PUMP_BTC_THRESHOLD:
            return ManipulationResult.CLEAN
        if spot_futures_ratio < FAKE_PUMP_RATIO_THRESHOLD:
            return ManipulationResult.FAKE_PUMP
        return ManipulationResult.CLEAN

    def check_stop_hunt(
        self,
        support_level: float,
        low_price: float,
        current_price: float,
        minutes_elapsed: float
    ) -> ManipulationResult:
        """
        Phát hiện stop-loss hunt: giá brief dip dưới support rồi phục hồi nhanh.
        Đây là BUY opportunity — whale vừa dọn hàng xong.
        """
        dip_pct = (support_level - low_price) / support_level
        recovered_above = current_price > support_level
        within_time = minutes_elapsed <= STOP_HUNT_MAX_MINUTES

        if dip_pct >= STOP_HUNT_DIP_THRESHOLD and recovered_above and within_time:
            return ManipulationResult.STOP_HUNT_REVERSAL
        return ManipulationResult.CLEAN

    def check_wash_trading(self, volume_ratio: float, trade_count_ratio: float) -> ManipulationResult:
        """
        Volume tăng nhiều nhưng số lượng trades tăng ít → vài lệnh lớn tự giao dịch với nhau.
        """
        if volume_ratio >= WASH_TRADE_VOLUME_MIN and trade_count_ratio < WASH_TRADE_COUNT_MAX:
            return ManipulationResult.WASH_TRADE
        return ManipulationResult.CLEAN

    def check_spoof_order(self, wall_size_usdt: float, wall_age_seconds: float) -> ManipulationResult:
        """Wall lớn xuất hiện rồi biến mất nhanh → spoof để đánh lừa bot."""
        if wall_size_usdt >= SPOOF_WALL_MIN_USDT and wall_age_seconds < SPOOF_MAX_AGE_SECONDS:
            return ManipulationResult.SPOOF_ORDER
        return ManipulationResult.CLEAN
