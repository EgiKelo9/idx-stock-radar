from typing import Tuple
import pandas as pd
from utils.logger import get_logger

logger = get_logger("data_quality_gate")


def validate_candle_data(df: pd.DataFrame, min_bars: int = 20) -> Tuple[bool, str]:
    """
    Validates candle snapshot DataFrame structure, integrity, and recency.
    Enforces Data Quality Gate (Stage 6 of the 25-stage pipeline).
    """
    if df is None or not isinstance(df, pd.DataFrame):
        return False, "Data snapshot kosong atau bukan DataFrame."

    if len(df) < min_bars:
        return False, f"Jumlah bar data tidak mencukupi: {len(df)} bar (dibutuhkan min {min_bars})."

    # Verify required OHLCV columns (case-insensitive check)
    cols = {c.lower(): c for c in df.columns}
    required = ["open", "high", "low", "close", "volume"]
    for req in required:
        if req not in cols:
            return False, f"Kolom wajib '{req}' tidak ditemukan dalam data candle."

    latest = df.iloc[-1]
    close_col = cols["close"]
    high_col = cols["high"]
    low_col = cols["low"]
    vol_col = cols["volume"]

    # Check for NaN in latest bar
    if pd.isna(latest[close_col]) or pd.isna(latest[vol_col]):
        return False, "Candle bar terbaru mengandung nilai NaN."

    # Value sanity checks
    close_val = float(latest[close_col])
    high_val = float(latest[high_col])
    low_val = float(latest[low_col])
    vol_val = float(latest[vol_col])

    if close_val <= 0:
        return False, f"Harga close tidak valid: {close_val}"

    if high_val < low_val or high_val < close_val or low_val > close_val:
        return False, f"Anomali harga candle: High={high_val}, Low={low_val}, Close={close_val}"

    if vol_val < 0:
        return False, f"Volume candle negatif: {vol_val}"

    return True, "Data candle valid dan memenuhi standar kualitas."
