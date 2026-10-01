from typing import Optional
from models.ticker import BrokerSummary
from models.sentiment import SentimentResult
from models.signal import TradingParameters


def calculate_confidence_score(
    setup_type: str,
    volume_multiplier: float,
    rsi: float,
    broker_summary: BrokerSummary,
    sentiment: SentimentResult,
    trading_plan: TradingParameters,
    market_regime: str = "NORMAL",
) -> float:
    """
    Computes holistic Composite Confidence Score (0 - 100) across 4 pillars:
    1. Technical Quality (0 - 30)
    2. Broker & Foreign Accumulation (0 - 30)
    3. AI Sentiment & Catalysts (0 - 20)
    4. Risk/Reward Math (0 - 20)
    Modulated by Market Regime factor.
    """
    score = 0.0

    # 1. Technical Pillar (Max 30)
    tech_score = 0.0
    if setup_type in ("BREAKOUT", "VOLUME_SURGE"):
        tech_score += 15.0
    elif setup_type in ("PULLBACK_REBOUND", "CONTRACTION_SETUP"):
        tech_score += 12.0
    elif setup_type == "OVERSOLD_BOUNCE":
        tech_score += 10.0

    if volume_multiplier >= 2.5:
        tech_score += 10.0
    elif volume_multiplier >= 1.8:
        tech_score += 7.0
    elif volume_multiplier >= 1.2:
        tech_score += 4.0

    if 40.0 <= rsi <= 65.0:
        tech_score += 5.0  # Healthy momentum range
    elif rsi < 35.0 or rsi > 75.0:
        tech_score += 2.0

    score += min(30.0, tech_score)

    # 2. Broker & Foreign Flow Pillar (Max 30)
    flow_score = 0.0
    accum_map = {
        "BIG_ACCUM": 18.0,
        "SMALL_ACCUM": 12.0,
        "NEUTRAL": 5.0,
        "DATA_N/A": 4.0,
        "SMALL_DIST": 1.0,
        "BIG_DIST": 0.0,
    }
    flow_score += accum_map.get(broker_summary.accum_rank, 4.0)

    foreign_map = {
        "HIGH_ACCUM": 12.0,
        "ACCUM": 8.0,
        "NEUTRAL": 4.0,
        "DATA_N/A": 3.0,
        "DIST": 0.0,
        "HIGH_DIST": 0.0,
    }
    flow_score += foreign_map.get(broker_summary.foreign_accum_rank, 3.0)

    score += min(30.0, flow_score)

    # 3. AI Sentiment Pillar (Max 20)
    sentiment_score = 0.0
    if sentiment.sentiment_label == "POSITIVE":
        sentiment_score = 15.0 + max(0.0, sentiment.sentiment_score * 5.0)
    elif sentiment.sentiment_label == "NEUTRAL":
        sentiment_score = 10.0
    elif sentiment.sentiment_label == "NEGATIVE":
        sentiment_score = 0.0

    if sentiment.catalyst_event in ("DIVIDEND_ANNOUNCEMENT", "FINANCIAL_REPORT", "CORPORATE_ACTION"):
        sentiment_score = min(20.0, sentiment_score + 3.0)

    score += min(20.0, sentiment_score)

    # 4. Risk / Reward Pillar (Max 20)
    rrr_score = 0.0
    rrr = trading_plan.rrr
    if rrr >= 3.0:
        rrr_score = 20.0
    elif rrr >= 2.5:
        rrr_score = 16.0
    elif rrr >= 2.0:
        rrr_score = 12.0
    else:
        rrr_score = 5.0

    score += min(20.0, rrr_score)

    # Market Regime Modulation
    if market_regime == "BEARISH":
        score -= 8.0  # Higher bar required in downtrending market
    elif market_regime == "BULLISH":
        score += 4.0  # Tailwind bonus

    return max(0.0, min(100.0, round(score, 1)))
