from datetime import datetime
from enum import Enum
from typing import Optional
from utils.market_calendar import MarketCalendar


class ScanContext(str, Enum):
    """
    Operational context for swing trader screening schedules:
    - PRE_MARKET: Evaluates D-1 settled closing candles & broker flow before market open (08:30 WIB).
    - MID_DAY: Evaluates Session 1 intraday action during lunch break (12:05 WIB).
    - END_MARKET: Evaluates settled EOD candles after market close (16:15 WIB) for next-day swing watchlist.
    """
    PRE_MARKET = "PRE_MARKET"
    MID_DAY = "MID_DAY"
    END_MARKET = "END_MARKET"

    @property
    def title_label(self) -> str:
        if self == ScanContext.PRE_MARKET:
            return "🌅 PRE-MARKET WATCHLIST"
        elif self == ScanContext.MID_DAY:
            return "☀️ MID-DAY MOMENTUM"
        else:
            return "🌙 SWING WATCHLIST — BESOK"

    @property
    def volume_threshold(self) -> float:
        """Volume multiplier threshold relative to 20-day average."""
        if self == ScanContext.MID_DAY:
            return 1.3  # Session 1 only, slightly relaxed
        return 1.5      # Full day settled threshold for PRE_MARKET and END_MARKET


def get_broker_reference_date(
    context: ScanContext,
    calendar: Optional[MarketCalendar] = None,
    current_dt: Optional[datetime] = None,
) -> str:
    """
    Returns reference date (YYYYMMDD) for broker flow queries according to scan context:
    - PRE_MARKET: Always uses D-1 settled trading day.
    - MID_DAY / END_MARKET: Uses current trading day. If current day is weekend/holiday, falls back to D-1.
    """
    cal = calendar or MarketCalendar()
    now_wib = cal.get_current_time(current_dt)

    if context == ScanContext.PRE_MARKET:
        prev_day = cal.get_previous_trading_day(now_wib)
        return prev_day.strftime("%Y%m%d")

    # For MID_DAY and END_MARKET:
    if cal.is_trading_day(now_wib):
        return now_wib.strftime("%Y%m%d")
    else:
        prev_day = cal.get_previous_trading_day(now_wib)
        return prev_day.strftime("%Y%m%d")
