from unittest.mock import MagicMock, patch
from models.scan_context import ScanContext
from models.ticker import Ticker
from scheduler import StockRadarScheduler


def test_scheduler_scan_market_cycle_contexts():
    app = StockRadarScheduler()

    mock_ticker = Ticker(symbol="BBCA", company_name="Bank Central Asia", board="UTAMA", avg_turnover_20d=5_000_000_000.0)
    app.ticker_fetcher.fetch_listed_tickers = MagicMock(return_value=[mock_ticker])
    app.pipeline.process_ticker = MagicMock(return_value=None)

    # Test PRE_MARKET
    app.scan_market_cycle(context=ScanContext.PRE_MARKET, force_run=True)
    app.pipeline.process_ticker.assert_called_with(mock_ticker, context=ScanContext.PRE_MARKET)

    # Test MID_DAY
    app.scan_market_cycle(context=ScanContext.MID_DAY, force_run=True)
    app.pipeline.process_ticker.assert_called_with(mock_ticker, context=ScanContext.MID_DAY)

    # Test END_MARKET
    app.scan_market_cycle(context=ScanContext.END_MARKET, force_run=True)
    app.pipeline.process_ticker.assert_called_with(mock_ticker, context=ScanContext.END_MARKET)
