import pytest
from social import SocialSignal


def make_signal():
    return SocialSignal(cryptopanic_key=None, lunarcrush_key=None)


# --- CryptoPanic sentiment ---

def test_sentiment_mostly_positive():
    s = make_signal()
    assert s.score_cryptopanic_sentiment(positive_count=7, negative_count=1, total_count=10) == 5


def test_sentiment_mostly_negative():
    s = make_signal()
    assert s.score_cryptopanic_sentiment(positive_count=1, negative_count=8, total_count=10) == 0


def test_sentiment_neutral_mixed():
    s = make_signal()
    assert s.score_cryptopanic_sentiment(positive_count=5, negative_count=4, total_count=10) == 2


def test_sentiment_too_few_news_zero():
    s = make_signal()
    # Less than 3 news = not meaningful
    assert s.score_cryptopanic_sentiment(positive_count=2, negative_count=0, total_count=2) == 0


def test_sentiment_exactly_at_bullish_threshold():
    s = make_signal()
    # 65% exactly = bullish
    assert s.score_cryptopanic_sentiment(positive_count=13, negative_count=2, total_count=20) == 5


# --- LunarCrush scoring ---

def test_lunarcrush_high_galaxy_viral():
    s = make_signal()
    # High galaxy + viral social volume
    assert s.score_lunarcrush(galaxy_score=75.0, social_volume_ratio=4.0) == 5


def test_lunarcrush_high_galaxy_normal_volume():
    s = make_signal()
    assert s.score_lunarcrush(galaxy_score=70.0, social_volume_ratio=1.0) == 3


def test_lunarcrush_low_galaxy():
    s = make_signal()
    assert s.score_lunarcrush(galaxy_score=25.0, social_volume_ratio=1.0) == 0


def test_lunarcrush_medium_galaxy():
    s = make_signal()
    assert s.score_lunarcrush(galaxy_score=50.0, social_volume_ratio=1.0) == 1


def test_lunarcrush_low_galaxy_spike_volume():
    s = make_signal()
    # No galaxy score but viral = some signal
    assert s.score_lunarcrush(galaxy_score=20.0, social_volume_ratio=3.5) == 2


def test_lunarcrush_capped_at_five():
    s = make_signal()
    # Max possible: galaxy=3 + volume=2 = 5
    result = s.score_lunarcrush(galaxy_score=90.0, social_volume_ratio=10.0)
    assert result == 5


# --- Total score ---

def test_total_score_max_is_10():
    s = make_signal()
    score = s.total_score(
        positive_count=8, negative_count=1, total_news=10,
        galaxy_score=80.0, social_volume_ratio=5.0
    )
    assert score == 10


def test_total_score_all_quiet_zero():
    s = make_signal()
    score = s.total_score(
        positive_count=0, negative_count=0, total_news=0,
        galaxy_score=10.0, social_volume_ratio=1.0
    )
    assert score == 0


# --- Fear & Greed scoring ---

def test_fear_greed_extreme_greed():
    s = make_signal()
    assert s.score_fear_greed(80) == 5

def test_fear_greed_greed():
    s = make_signal()
    assert s.score_fear_greed(65) == 4

def test_fear_greed_neutral():
    s = make_signal()
    assert s.score_fear_greed(50) == 2

def test_fear_greed_fear():
    s = make_signal()
    assert s.score_fear_greed(35) == 1

def test_fear_greed_extreme_fear():
    s = make_signal()
    assert s.score_fear_greed(10) == 0

def test_fear_greed_boundary_extreme_greed():
    s = make_signal()
    assert s.score_fear_greed(75) == 5

def test_fear_greed_boundary_greed():
    s = make_signal()
    assert s.score_fear_greed(55) == 4


# --- CoinGecko sentiment scoring ---

def test_coingecko_bullish():
    s = make_signal()
    assert s.score_coingecko_sentiment(70.0) == 3

def test_coingecko_neutral():
    s = make_signal()
    assert s.score_coingecko_sentiment(55.0) == 1

def test_coingecko_bearish():
    s = make_signal()
    assert s.score_coingecko_sentiment(40.0) == 0

def test_coingecko_exactly_at_bullish_threshold():
    s = make_signal()
    assert s.score_coingecko_sentiment(65.0) == 3


# --- get_social_score orchestrator ---

def test_get_social_score_no_keys_uses_fg_and_cg(monkeypatch):
    """Không có API key vẫn có điểm từ Fear&Greed + CoinGecko."""
    s = make_signal()
    monkeypatch.setattr(s, "get_fear_greed_index", lambda: 72)      # Greed → 4 pts
    monkeypatch.setattr(s, "get_coingecko_sentiment", lambda sym: 68.0)  # Bullish → 3 pts
    score = s.get_social_score("BTCUSDT")
    assert score == 7  # 4 + 3

def test_get_social_score_capped_at_10(monkeypatch):
    s = make_signal()
    monkeypatch.setattr(s, "get_fear_greed_index", lambda: 90)      # 5 pts
    monkeypatch.setattr(s, "get_coingecko_sentiment", lambda sym: 80.0)  # 3 pts
    score = s.get_social_score("BTCUSDT")
    assert score <= 10

def test_get_social_score_extreme_fear(monkeypatch):
    s = make_signal()
    monkeypatch.setattr(s, "get_fear_greed_index", lambda: 10)      # 0 pts
    monkeypatch.setattr(s, "get_coingecko_sentiment", lambda sym: 35.0)  # 0 pts
    score = s.get_social_score("BTCUSDT")
    assert score == 0
