from datetime import datetime
from utils.market_calendar import MarketCalendar


def test_market_calendar_weekdays_and_sessions():
    cal = MarketCalendar()

    # Wednesday 10:30 WIB -> SESSION_1 (Open)
    wed_s1 = datetime(2026, 3, 25, 10, 30)
    assert cal.get_current_session(wed_s1) == "SESSION_1"
    assert cal.is_market_open(wed_s1) is True

    # Wednesday 12:30 WIB -> Break time (Closed)
    wed_break = datetime(2026, 3, 25, 12, 30)
    assert cal.get_current_session(wed_break) == "CLOSED"
    assert cal.is_market_open(wed_break) is False

    # Wednesday 14:15 WIB -> SESSION_2 (Open)
    wed_s2 = datetime(2026, 3, 25, 14, 15)
    assert cal.get_current_session(wed_s2) == "SESSION_2"
    assert cal.is_market_open(wed_s2) is True

    # Wednesday 16:30 WIB -> Market closed
    wed_after = datetime(2026, 3, 25, 16, 30)
    assert cal.get_current_session(wed_after) == "CLOSED"
    assert cal.is_market_open(wed_after) is False


def test_market_calendar_weekends_and_holidays():
    cal = MarketCalendar()

    # Sunday 10:00 WIB
    sunday = datetime(2026, 3, 22, 10, 0)
    assert cal.is_weekend(sunday) is True
    assert cal.get_current_session(sunday) == "CLOSED"

    # Known holiday: 2026-01-01 (New Year)
    holiday = datetime(2026, 1, 1, 10, 0)
    assert cal.is_holiday(holiday) is True
    assert cal.get_current_session(holiday) == "CLOSED"


def test_is_trading_day_and_previous_day():
    cal = MarketCalendar()

    # Wednesday is a trading day
    wed = datetime(2026, 3, 25, 10, 30)
    assert cal.is_trading_day(wed) is True

    # Sunday is not a trading day
    sun = datetime(2026, 3, 22, 10, 0)
    assert cal.is_trading_day(sun) is False

    # Previous trading day from Monday 2026-03-23 should be Friday 2026-03-20
    mon = datetime(2026, 3, 23, 8, 30)
    prev = cal.get_previous_trading_day(mon)
    assert prev.weekday() == 4  # Friday
    assert prev.day == 20

