from datetime import datetime
from zoneinfo import ZoneInfo
from models.scan_context import ScanContext, get_broker_reference_date
from utils.market_calendar import MarketCalendar


def test_scan_context_properties():
    assert ScanContext.PRE_MARKET.volume_threshold == 1.5
    assert ScanContext.MID_DAY.volume_threshold == 1.3
    assert ScanContext.END_MARKET.volume_threshold == 1.5

    assert "PRE-MARKET" in ScanContext.PRE_MARKET.title_label
    assert "MID-DAY" in ScanContext.MID_DAY.title_label
    assert "SWING WATCHLIST" in ScanContext.END_MARKET.title_label


def test_get_broker_reference_date():
    cal = MarketCalendar()
    wib = ZoneInfo("Asia/Jakarta")

    # Tuesday morning at 08:30 WIB
    dt_tue = datetime(2026, 9, 15, 8, 30, tzinfo=wib)

    # PRE_MARKET must always return D-1 settled date (Monday 2026-09-14)
    ref_pre = get_broker_reference_date(ScanContext.PRE_MARKET, calendar=cal, current_dt=dt_tue)
    assert ref_pre == "20260914"

    # MID_DAY on Tuesday must return Tuesday (2026-09-15)
    ref_mid = get_broker_reference_date(ScanContext.MID_DAY, calendar=cal, current_dt=dt_tue)
    assert ref_mid == "20260915"

    # Sunday morning -> PRE_MARKET & MID_DAY must return Friday
    dt_sun = datetime(2026, 9, 13, 10, 0, tzinfo=wib)
    ref_sun = get_broker_reference_date(ScanContext.MID_DAY, calendar=cal, current_dt=dt_sun)
    assert ref_sun == "20260911"
