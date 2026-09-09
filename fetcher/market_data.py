from typing import Optional, Tuple
import pandas as pd
from utils.logger import get_logger
from utils.retry import retry_sync

logger = get_logger("market_data_fetcher")


class MarketDataFetcher:
    def __init__(self):
        pass

    @staticmethod
    def format_symbol(ticker: str) -> str:
        """Ensures symbol ends with .JK suffix for IDX stocks."""
        clean = ticker.strip().upper().replace(".JK", "")
        return f"{clean}.JK"

    @retry_sync(max_attempts=3, delays=(2.0, 4.0, 8.0))
    def fetch_historical_daily(self, ticker: str, period: str = "60d") -> Optional[pd.DataFrame]:
        """
        Fetches daily historical candles for rolling metrics (SMA, ATR, Avg Volume).
        """
        try:
            import yfinance as yf
            symbol = self.format_symbol(ticker)
            t = yf.Ticker(symbol)
            df = t.history(period=period, interval="1d")
            if df.empty or len(df) < 20:
                logger.warning(f"Insufficient historical data for {ticker}: {len(df)} rows")
                return None

            df = df.reset_index()
            # Standardize column naming
            df.columns = [c.lower() for c in df.columns]
            return df
        except Exception as e:
            logger.error(f"Error fetching daily historical for {ticker}: {e}")
            raise

    @retry_sync(max_attempts=3, delays=(2.0, 4.0, 8.0))
    def fetch_intraday(self, ticker: str, interval: str = "15m", period: str = "5d") -> Optional[pd.DataFrame]:
        """
        Fetches intraday bars (e.g. 15m interval) for the current active trading session.
        """
        try:
            import yfinance as yf
            symbol = self.format_symbol(ticker)
            t = yf.Ticker(symbol)
            df = t.history(period=period, interval=interval)
            if df.empty:
                logger.warning(f"Empty intraday data for {ticker}")
                return None

            df = df.reset_index()
            df.columns = [c.lower() for c in df.columns]
            return df
        except Exception as e:
            logger.error(f"Error fetching intraday data for {ticker}: {e}")
            raise

    def get_market_snapshot(self, ticker: str) -> Optional[Tuple[pd.DataFrame, float, float, float]]:
        """
        Returns (historical_df, current_price, current_volume, avg_volume_20d).
        """
        df = self.fetch_historical_daily(ticker, period="60d")
        if df is None or len(df) < 20:
            return None

        # 20-day average volume (excluding current in-progress bar if needed)
        avg_vol_20d = float(df["volume"].iloc[-21:-1].mean()) if len(df) >= 21 else float(df["volume"].mean())
        latest = df.iloc[-1]
        current_price = float(latest["close"])
        current_volume = float(latest["volume"])

        return df, current_price, current_volume, avg_vol_20d
