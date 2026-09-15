from datetime import datetime, time, date, timedelta
from functools import lru_cache
from typing import Optional, Set
import zoneinfo

try:
    import holidays
    HAS_HOLIDAYS_LIB = True
except ImportError:
    HAS_HOLIDAYS_LIB = False


@lru_cache(maxsize=16)
def _get_dynamic_holidays(year: int) -> Set[str]:
    """Dynamically generates Indonesian public holidays for any given year."""
    holiday_set: Set[str] = set()
    if HAS_HOLIDAYS_LIB:
        id_h = holidays.country_holidays("ID", years=[year])
        for d in id_h.keys():
            holiday_set.add(d.strftime("%Y-%m-%d"))
    return holiday_set


class MarketCalendar:
    def __init__(
        self,
        timezone_str: str = "Asia/Jakarta",
        holidays: Optional[Set[str]] = None,
    ):
        self.tz = zoneinfo.ZoneInfo(timezone_str)
        self.custom_holidays = set(holidays) if holidays is not None else set()

    def get_current_time(self, dt: Optional[datetime] = None) -> datetime:
        """Returns the datetime localized to Jakarta timezone."""
        if dt is None:
            return datetime.now(self.tz)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=self.tz)
        return dt.astimezone(self.tz)

    def is_holiday(self, dt: Optional[datetime] = None) -> bool:
        """
        Checks if given date is an official exchange or national holiday dynamically.
        Uses the python holidays library to generate the holiday calendar for any year on demand.
        """
        current = self.get_current_time(dt)
        date_str = current.strftime("%Y-%m-%d")

        if date_str in self.custom_holidays:
            return True

        dynamic_holidays = _get_dynamic_holidays(current.year)
        return date_str in dynamic_holidays

    def is_weekend(self, dt: Optional[datetime] = None) -> bool:
        """Saturday (5) and Sunday (6) are non-trading days."""
        current = self.get_current_time(dt)
        return current.weekday() >= 5

    def is_trading_day(self, dt: Optional[datetime] = None) -> bool:
        """Returns True if the date is not a weekend and not a holiday."""
        current = self.get_current_time(dt)
        return not self.is_weekend(current) and not self.is_holiday(current)

    def get_previous_trading_day(self, dt: Optional[datetime] = None) -> datetime:
        """Returns the most recent previous trading day datetime (localized to Jakarta timezone)."""
        current = self.get_current_time(dt)
        prev = current - timedelta(days=1)
        while not self.is_trading_day(prev):
            prev -= timedelta(days=1)
        return prev

    def get_current_session(self, dt: Optional[datetime] = None) -> str:
        """
        Determines current trading session:
        Returns: 'SESSION_1', 'SESSION_2', or 'CLOSED'
        """
        current = self.get_current_time(dt)

        if self.is_weekend(current) or self.is_holiday(current):
            return "CLOSED"

        curr_time = current.time()
        is_friday = current.weekday() == 4

        # Session 1
        s1_start = time(9, 0)
        s1_end = time(11, 30) if is_friday else time(12, 0)
        if s1_start <= curr_time <= s1_end:
            return "SESSION_1"

        # Session 2
        s2_start = time(14, 0) if is_friday else time(13, 30)
        s2_end = time(16, 0)
        if s2_start <= curr_time <= s2_end:
            return "SESSION_2"

        return "CLOSED"

    def is_market_open(self, dt: Optional[datetime] = None) -> bool:
        """Returns True if the market is currently active in Session I or Session II."""
        return self.get_current_session(dt) in ("SESSION_1", "SESSION_2")
