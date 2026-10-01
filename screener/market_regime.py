from dataclasses import dataclass
from typing import Optional, Literal
import pandas as pd
import yfinance as yf
from utils.logger import get_logger

logger = get_logger("market_regime")

RegimeType = Literal["BULLISH", "BEARISH", "SIDEWAYS", "VOLATILE", "NORMAL"]


@dataclass(frozen=True)
class MarketRegimeResult:
    regime: RegimeType
    ihsg_price: float
    sma_20: float
    sma_50: float
    change_pct_5d: float
    description: str


class MarketRegimeDetector:
    def __init__(self, ticker_symbol: str = "^JKSE"):
        self.ticker_symbol = ticker_symbol
        self._cached_regime: Optional[MarketRegimeResult] = None

    def detect_regime(self, force_refresh: bool = False) -> MarketRegimeResult:
        """
        Evaluates Indonesia Composite Index (IHSG / ^JKSE) macro trend.
        Classifies regime to modulate screener aggressiveness and confidence thresholds.
        """
        if self._cached_regime and not force_refresh:
            return self._cached_regime

        try:
            ticker = yf.Ticker(self.ticker_symbol)
            df = ticker.history(period="3mo", interval="1d")
            if df is None or len(df) < 25:
                logger.warning("Insufficient IHSG historical data for regime detection, returning NORMAL")
                return MarketRegimeResult(
                    regime="NORMAL",
                    ihsg_price=0.0,
                    sma_20=0.0,
                    sma_50=0.0,
                    change_pct_5d=0.0,
                    description="Data IHSG tidak mencukupi, menggunakan regime default."
                )

            close_series = df["Close"]
            current_price = float(close_series.iloc[-1])
            sma20 = float(close_series.rolling(20).mean().iloc[-1])
            sma50 = float(close_series.rolling(50).mean().iloc[-1]) if len(df) >= 50 else sma20

            price_5d_ago = float(close_series.iloc[-5]) if len(df) >= 5 else current_price
            change_5d = round(((current_price - price_5d_ago) / price_5d_ago) * 100, 2)

            # Regime classification logic
            if current_price > sma20 and sma20 >= sma50:
                regime = "BULLISH"
                desc = f"IHSG Uptrend di atas SMA20 ({current_price:.1f} > {sma20:.1f}). Pasar kondusif untuk swing."
            elif current_price < sma20 and sma20 <= sma50:
                regime = "BEARISH"
                desc = f"IHSG Downtrend di bawah SMA20 ({current_price:.1f} < {sma20:.1f}). Screening defensif aktif."
            else:
                regime = "SIDEWAYS"
                desc = f"IHSG Konsolidasi ({current_price:.1f} di sekitar SMA20/50). Seleksi ketat pada breakout volume."

            result = MarketRegimeResult(
                regime=regime,
                ihsg_price=round(current_price, 2),
                sma_20=round(sma20, 2),
                sma_50=round(sma50, 2),
                change_pct_5d=change_5d,
                description=desc,
            )
            self._cached_regime = result
            logger.info(f"Market Regime evaluated: {regime} (IHSG: {current_price:.1f})")
            return result

        except Exception as e:
            logger.warning(f"Failed to detect market regime via {self.ticker_symbol}: {e}")
            return MarketRegimeResult(
                regime="NORMAL",
                ihsg_price=0.0,
                sma_20=0.0,
                sma_50=0.0,
                change_pct_5d=0.0,
                description="Deteksi pasar makro error, fallback NORMAL."
            )
