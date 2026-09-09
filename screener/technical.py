from typing import Optional, Tuple
import numpy as np
import pandas as pd
from models.signal import SetupType


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

    # 20-period highest high (Resistance level)
    data["resistance_20"] = data["high"].shift(1).rolling(window=20).max()

    # Relative Strength Index (RSI - Wilder's Smoothing)
    delta = data["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / rsi_period, min_periods=rsi_period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / rsi_period, min_periods=rsi_period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    data["rsi"] = 100 - (100 / (1 + rs))
    data["rsi"] = data["rsi"].fillna(50.0)

    # Average True Range (ATR 14 - Wilder's)
    prev_close = data["close"].shift(1)
    tr1 = data["high"] - data["low"]
    tr2 = (data["high"] - prev_close).abs()
    tr3 = (data["low"] - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    data["atr"] = tr.ewm(alpha=1 / atr_period, min_periods=atr_period, adjust=False).mean()

    return data


def detect_technical_setup(
    df: pd.DataFrame,
    volume_multiplier: float,
) -> Tuple[Optional[SetupType], dict]:
    """
    Identifies if the latest bar satisfies technical entry conditions.
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

    # Setup 1: Breakout (Close breaks above 20-day resistance with strong volume)
    if close > res20 and volume_multiplier >= 1.5 and rsi <= 75:
        return "BREAKOUT", metrics

    # Setup 2: Pullback Rebound (Above SMA 20/50, bullish candle bouncing off support)
    # Price tested near SMA 20 (within 2%) and closed above SMA 20, bullish bar
    near_sma20 = abs(close - sma20) / sma20 <= 0.03
    is_bullish_bar = close > open_p and close > prev["close"]
    if close >= sma20 and near_sma20 and is_bullish_bar and 40 <= rsi <= 65:
        return "PULLBACK_REBOUND", metrics

    # Setup 3: Oversold Bounce (RSI < 35 reversing up with bullish candle)
    if rsi < 35 and is_bullish_bar and volume_multiplier >= 1.2:
        return "OVERSOLD_BOUNCE", metrics

    # Generic strong momentum volume surge if above SMA 20
    if volume_multiplier >= 2.0 and is_bullish_bar and close > sma20 and rsi <= 70:
        return "VOLUME_SURGE", metrics

    return None, metrics
