import argparse
import sys
from typing import Optional
from apscheduler.schedulers.blocking import BlockingScheduler
from config import config
from db import DatabaseManager
from fetcher.ticker_list import TickerListFetcher
from models.scan_context import ScanContext
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
            f"Configured 3 Swing Trading Schedules: "
            f"Pre-Market {config.system.pre_market_hour:02d}:{config.system.pre_market_minute:02d}, "
            f"Mid-Day {config.system.mid_day_hour:02d}:{config.system.mid_day_minute:02d}, "
            f"End-Market {config.system.end_market_hour:02d}:{config.system.end_market_minute:02d} "
            f"({config.system.timezone})"
        )

    def scan_market_cycle(
        self,
        context: Optional[ScanContext] = None,
        force_run: bool = False,
    ):
        """
        Executes one full market scan across the active ticker universe for a specific context.
        """
        active_context = context or ScanContext.MID_DAY
        now = self.calendar.get_current_time()

        if not force_run and not self.calendar.is_trading_day(now):
            logger.info(
                f"Today ({now.strftime('%Y-%m-%d')}) is not an IDX trading day (Weekend/Holiday). "
                f"Skipping {active_context.value} scan."
            )
            return

        logger.info(
            f"Starting {active_context.value} market scan cycle at {now.strftime('%Y-%m-%d %H:%M:%S %Z')} "
            f"[{active_context.title_label}]"
        )
        tickers = self.ticker_fetcher.fetch_listed_tickers()
        logger.info(f"Loaded {len(tickers)} candidates for {active_context.value} screening.")

        signals_generated = 0
        for ticker in tickers:
            try:
                sig = self.pipeline.process_ticker(ticker, context=active_context)
                if sig is not None:
                    signals_generated += 1
            except Exception as e:
                logger.error(f"Error processing {ticker.symbol}: {e}")

        logger.info(f"{active_context.value} scan cycle finished. Signals dispatched: {signals_generated}")

    def start(self):
        """Starts the blocking scheduled job loop with 3 fixed swing trading cron triggers."""
        self.startup()

        # Job 1: Pre-Market Scan (Mon-Fri, default 08:30 WIB)
        self.scheduler.add_job(
            self.scan_market_cycle,
            "cron",
            day_of_week="mon-fri",
            hour=config.system.pre_market_hour,
            minute=config.system.pre_market_minute,
            kwargs={"context": ScanContext.PRE_MARKET},
            id="scan_pre_market",
            replace_existing=True,
        )

        # Job 2: Mid-Day Break Scan (Mon-Fri, default 12:05 WIB)
        self.scheduler.add_job(
            self.scan_market_cycle,
            "cron",
            day_of_week="mon-fri",
            hour=config.system.mid_day_hour,
            minute=config.system.mid_day_minute,
            kwargs={"context": ScanContext.MID_DAY},
            id="scan_mid_day",
            replace_existing=True,
        )

        # Job 3: End-Market Scan (Mon-Fri, default 16:15 WIB)
        self.scheduler.add_job(
            self.scan_market_cycle,
            "cron",
            day_of_week="mon-fri",
            hour=config.system.end_market_hour,
            minute=config.system.end_market_minute,
            kwargs={"context": ScanContext.END_MARKET},
            id="scan_end_market",
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
    parser.add_argument(
        "--context",
        type=str,
        choices=["pre_market", "mid_day", "end_market"],
        default="mid_day",
        help="Scan context to execute with --run-once: pre_market, mid_day, or end_market (default: mid_day)",
    )
    args = parser.parse_args()

    app = StockRadarScheduler()

    if args.run_once:
        app.startup()
        ctx_map = {
            "pre_market": ScanContext.PRE_MARKET,
            "mid_day": ScanContext.MID_DAY,
            "end_market": ScanContext.END_MARKET,
        }
        chosen_ctx = ctx_map.get(args.context.lower(), ScanContext.MID_DAY)
        logger.info(f"Running single immediate scan cycle (--run-once, context={chosen_ctx.value})...")
        app.scan_market_cycle(context=chosen_ctx, force_run=True)
    else:
        app.start()


if __name__ == "__main__":
    main()
