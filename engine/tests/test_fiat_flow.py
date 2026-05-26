import pytest
from fiat_flow import FiatFlowTracker


def make_tracker():
    return FiatFlowTracker(whale_alert_api_key=None)


# --- USDT volume scoring ---

def test_usdt_volume_spike_high():
    t = make_tracker()
    assert t.score_usdt_volume(current_volume=3_000_000, avg_volume_24h=1_000_000) == 10


def test_usdt_volume_spike_medium():
    t = make_tracker()
    assert t.score_usdt_volume(current_volume=2_000_000, avg_volume_24h=1_000_000) == 5


def test_usdt_volume_normal_zero():
    t = make_tracker()
    assert t.score_usdt_volume(current_volume=1_200_000, avg_volume_24h=1_000_000) == 0


def test_usdt_volume_zero_avg_safe():
    t = make_tracker()
    assert t.score_usdt_volume(current_volume=5_000_000, avg_volume_24h=0) == 0


def test_usdt_volume_exactly_at_high_threshold():
    t = make_tracker()
    # 3.0x exactly = high
    assert t.score_usdt_volume(current_volume=3_000_000, avg_volume_24h=1_000_000) == 10


# --- Whale transfer scoring ---

def test_large_withdrawal_to_wallet_bullish():
    t = make_tracker()
    transfers = [{"amount_usd": 15_000_000, "to_type": "wallet"}]
    assert t.score_whale_transfers(transfers) == 5


def test_medium_withdrawal_to_wallet():
    t = make_tracker()
    transfers = [{"amount_usd": 2_000_000, "to_type": "wallet"}]
    assert t.score_whale_transfers(transfers) == 2


def test_large_deposit_to_exchange_bearish():
    t = make_tracker()
    transfers = [{"amount_usd": 15_000_000, "to_type": "exchange"}]
    # Bearish but clamped to 0
    assert t.score_whale_transfers(transfers) == 0


def test_mixed_transfers_net_positive():
    t = make_tracker()
    transfers = [
        {"amount_usd": 15_000_000, "to_type": "wallet"},   # +5
        {"amount_usd": 2_000_000, "to_type": "exchange"},   # -1
    ]
    assert t.score_whale_transfers(transfers) == 4


def test_empty_transfers_zero():
    t = make_tracker()
    assert t.score_whale_transfers([]) == 0


def test_transfers_capped_at_five():
    t = make_tracker()
    # Many large withdrawals — capped at 5
    transfers = [
        {"amount_usd": 50_000_000, "to_type": "wallet"},
        {"amount_usd": 50_000_000, "to_type": "wallet"},
        {"amount_usd": 50_000_000, "to_type": "wallet"},
    ]
    assert t.score_whale_transfers(transfers) == 5


# --- Total score ---

def test_total_score_max_is_15():
    t = make_tracker()
    score = t.total_score(
        current_volume=5_000_000,
        avg_volume_24h=1_000_000,
        transfers=[{"amount_usd": 20_000_000, "to_type": "wallet"}]
    )
    assert score == 15


def test_total_score_no_activity_zero():
    t = make_tracker()
    score = t.total_score(
        current_volume=1_000_000,
        avg_volume_24h=1_000_000,
        transfers=[]
    )
    assert score == 0
