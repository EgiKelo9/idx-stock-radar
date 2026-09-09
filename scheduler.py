import argparse
import signal
import sys
from apscheduler.schedulers.blocking import BlockingScheduler
from config import config
from db import DatabaseManager
from fetcher.ticker_list import TickerListFetcher
from pipeline import SignalPipeline
from utils.logger import get_logger
from utils.market_calendar import MarketCalendar

logger = get_logger("market_scheduler")


class StockRadarScheduler:
    def __init__(self):
        self.calendar = MarketCalendar(timezone_str=config.system.timezone)
        self.ticker_fetcher = TickerListFetcher()
        self.pipeline = SignalPipeline()
        self.db = DatabaseManager()
        self.scheduler = BlockingScheduler(timezone=config.system.timezone)

    def startup(self):
        """Initializes database schema and prepares state."""
        logger.info("Initializing IDX Stock Radar System...")
        self.db.initialize_schema()
        logger.info(
            f"Configured Scan Interval: {config.system.scan_interval_minutes} minutes, "
            f"Timezone: {config.system.timezone}"
        )

    def scan_market_cycle(self, force_run: bool = False):
        """
        Executes one full market scan across the active ticker universe.
        """
        now = self.calendar.get_current_time()
        session = self.calendar.get_current_session(now)

        if not force_run and not self.calendar.is_market_open(now):
            logger.info(f"Market is currently CLOSED (Session: {session}). Skipping scan.")
            return

        logger.info(f"Starting market scan cycle at {now.strftime('%Y-%m-%d %H:%M:%S %Z')} (Session: {session})")
        tickers = self.ticker_fetcher.fetch_listed_tickers()
        logger.info(f"Loaded {len(tickers)} candidates for screening.")

        signals_generated = 0
        for ticker in tickers:
            try:
                sig = self.pipeline.process_ticker(ticker)
                if sig is not None:
                    signals_generated += 1
            except Exception as e:
                logger.error(f"Error processing {ticker.symbol}: {e}")

        logger.info(f"Scan cycle finished. Signals dispatched: {signals_generated}")

    def start(self):
        """Starts the blocking scheduled job loop."""
        self.startup()

        # Add recurring interval job
        self.scheduler.add_job(
            self.scan_market_cycle,
            "interval",
            minutes=config.system.scan_interval_minutes,
            id="idx_market_scanner",
            replace_existing=True,
        )

        logger.info("Scheduler loop started. Waiting for next market session trigger...")
        try:
            self.scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("Scheduler stopped by user/signal.")


def main():
    parser = argparse.ArgumentParser(description="IDX Stock Radar AI Automation Bot")
    parser.add_argument(
        "--run-once",
        action="store_true",
        help="Executes a single market scan cycle immediately (bypassing session hours for testing).",
    )
    args = parser.parse_args()

    app = StockRadarScheduler()

    if args.run_once:
        app.startup()
        logger.info("Running single immediate scan cycle (--run-once)...")
        app.scan_market_cycle(force_run=True)
    else:
        app.start()


if __name__ == "__main__":
    main()
