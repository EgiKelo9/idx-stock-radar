from typing import Optional, Tuple
import numpy as np
import pandas as pd
from models.signal import SetupType
from models.scan_context import ScanContext


def calculate_indicators(
    df: pd.DataFrame,
    rsi_period: int = 14,
    atr_period: int = 14,
    sma_fast: int = 20,
    sma_mid: int = 50,
    sma_slow: int = 200,
) -> pd.DataFrame:
    """
    Computes technical indicators on OHLCV DataFrame using robust vectorized Pandas.
    Expects columns: ['open', 'high', 'low', 'close', 'volume'].
    """
    data = df.copy()
    data.columns = [c.lower() for c in data.columns]

    # Simple Moving Averages
    data[f"sma_{sma_fast}"] = data["close"].rolling(window=sma_fast).mean()
    data[f"sma_{sma_mid}"] = data["close"].rolling(window=sma_mid).mean()
    data[f"sma_{sma_slow}"] = data["close"].rolling(window=sma_slow).mean()

    # Resistance: Highest high over 20 periods
    data["resistance_20"] = data["high"].rolling(window=20).max()

    # Relative Strength Index (RSI 14) via Wilder's Exponential Smoothing
    delta = data["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(com=rsi_period - 1, min_periods=rsi_period).mean()
    avg_loss = loss.ewm(com=rsi_period - 1, min_periods=rsi_period).mean()

    rs = avg_gain / (avg_loss + 1e-9)
    data["rsi"] = 100 - (100 / (1 + rs))

    # Average True Range (ATR 14)
    tr1 = data["high"] - data["low"]
    tr2 = (data["high"] - data["close"].shift(1)).abs()
    tr3 = (data["low"] - data["close"].shift(1)).abs()
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    data["atr"] = true_range.rolling(window=atr_period).mean()

    return data


def detect_technical_setup(
    df: pd.DataFrame,
    volume_multiplier: float,
    context: Optional[ScanContext] = None,
) -> Tuple[Optional[SetupType], dict]:
    """
    Identifies if the latest bar satisfies technical entry conditions based on context.
    - PRE_MARKET: BREAKOUT, PULLBACK_REBOUND, OVERSOLD_BOUNCE (RSI <= 70)
    - MID_DAY: BREAKOUT, VOLUME_SURGE (RSI <= 68)
    - END_MARKET: All setups + CONTRACTION_SETUP (RSI <= 72)
    Returns: (SetupType or None, indicator_metrics: dict)
    """
    if len(df) < 50:
        return None, {}

    last = df.iloc[-1]
    prev = df.iloc[-2]

    close = float(last["close"])
    open_p = float(last["open"])
    high = float(last["high"])
    low = float(last["low"])
    rsi = float(last["rsi"])
    atr = float(last["atr"]) if not np.isnan(last["atr"]) else (high - low)

    sma20 = float(last["sma_20"]) if not np.isnan(last["sma_20"]) else close
    sma50 = float(last["sma_50"]) if not np.isnan(last["sma_50"]) else close
    res20 = float(last["resistance_20"]) if not np.isnan(last["resistance_20"]) else high

    metrics = {
        "close": close,
        "rsi": round(rsi, 1),
        "atr": round(atr, 2),
        "sma_20": round(sma20, 2),
        "sma_50": round(sma50, 2),
        "resistance_20": round(res20, 2),
        "volume_multiplier": volume_multiplier,
    }

    # Contextual RSI Caps
    if context == ScanContext.PRE_MARKET:
        rsi_cap = 70.0
    elif context == ScanContext.MID_DAY:
        rsi_cap = 68.0
    elif context == ScanContext.END_MARKET:
        rsi_cap = 72.0
    else:
        rsi_cap = 75.0

    if rsi > rsi_cap:
        return None, metrics

    near_sma20 = abs(close - sma20) / sma20 <= 0.03
    is_bullish_bar = close > open_p and close > prev["close"]

    detected_setup: Optional[SetupType] = None

    # Setup: Contraction Setup (Inside bar with drying volume <= 0.7x + above SMA20) - special for swing watchlist
    is_inside_bar = high <= float(prev["high"]) and low >= float(prev["low"])
    if (
        (context is None or context == ScanContext.END_MARKET)
        and is_inside_bar
        and volume_multiplier <= 0.7
        and close >= sma20
    ):
        detected_setup = "CONTRACTION_SETUP"

    # Setup 1: Breakout (Close breaks above 20-day resistance with strong volume)
    elif close > res20 and volume_multiplier >= 1.5:
        detected_setup = "BREAKOUT"

    # Setup 2: Pullback Rebound (Above SMA 20/50, bullish candle bouncing off support)
    elif close >= sma20 and near_sma20 and is_bullish_bar and 40 <= rsi <= 65:
        detected_setup = "PULLBACK_REBOUND"

    # Setup 3: Oversold Bounce (RSI < 35 reversing up with bullish candle)
    elif rsi < 35 and is_bullish_bar and volume_multiplier >= 1.2:
        detected_setup = "OVERSOLD_BOUNCE"

    # Setup 4: Generic strong momentum volume surge if above SMA 20
    elif volume_multiplier >= 2.0 and is_bullish_bar and close > sma20:
        detected_setup = "VOLUME_SURGE"

    if detected_setup is None:
        return None, metrics

    # Enforce context setup constraints
    if context == ScanContext.PRE_MARKET:
        allowed_pre = {"BREAKOUT", "PULLBACK_REBOUND", "OVERSOLD_BOUNCE"}
        if detected_setup not in allowed_pre:
            return None, metrics
    elif context == ScanContext.MID_DAY:
        allowed_mid = {"BREAKOUT", "VOLUME_SURGE"}
        if detected_setup not in allowed_mid:
            return None, metrics

    return detected_setup, metrics
