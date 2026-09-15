from typing import Optional
from analyzer.sentiment import LLMSentimentAnalyzer
from config import config
from db import DatabaseManager
from fetcher.broker_flow import BrokerFlowFetcher
from fetcher.disclosure import DisclosureFetcher
from fetcher.market_data import MarketDataFetcher
from models.scan_context import ScanContext, get_broker_reference_date
from models.signal import SignalMetrics, SignalPayload
from models.ticker import Ticker
from notifier.telegram import TelegramNotifier
from risk_engine.tick_size import is_near_ara
from risk_engine.trading_plan import generate_trading_plan
from screener.eligibility import check_ticker_eligibility
from screener.technical import calculate_indicators, detect_technical_setup
from screener.volume_spike import check_volume_spike
from utils.logger import get_logger

logger = get_logger("signal_pipeline")


class SignalPipeline:
    def __init__(
        self,
        market_fetcher: Optional[MarketDataFetcher] = None,
        broker_fetcher: Optional[BrokerFlowFetcher] = None,
        disclosure_fetcher: Optional[DisclosureFetcher] = None,
        sentiment_analyzer: Optional[LLMSentimentAnalyzer] = None,
        notifier: Optional[TelegramNotifier] = None,
        db: Optional[DatabaseManager] = None,
    ):
        self.market_fetcher = market_fetcher or MarketDataFetcher()
        self.broker_fetcher = broker_fetcher or BrokerFlowFetcher()
        self.disclosure_fetcher = disclosure_fetcher or DisclosureFetcher()
        self.sentiment_analyzer = sentiment_analyzer or LLMSentimentAnalyzer()
        self.notifier = notifier or TelegramNotifier()
        self.db = db or DatabaseManager()

    def process_ticker(
        self,
        ticker: Ticker,
        context: Optional[ScanContext] = None,
    ) -> Optional[SignalPayload]:
        """
        Executes multi-layer screening and risk evaluation for a single ticker under a specific scan context.
        Returns SignalPayload if all criteria pass, else None.
        """
        active_context = context or ScanContext.MID_DAY
        symbol = ticker.clean_symbol

        # Layer 0: Eligibility Hard Filter (FCA, Suspended, Turnover)
        is_eligible, elig_reason = check_ticker_eligibility(ticker)
        if not is_eligible:
            logger.debug(f"[{symbol}] Ineligible: {elig_reason}")
            return None

        # Fetch market snapshot
        snapshot = self.market_fetcher.get_market_snapshot(symbol)
        if snapshot is None:
            logger.debug(f"[{symbol}] Failed to retrieve market data")
            return None

        df, current_price, current_volume, avg_vol_20d = snapshot
        turnover = current_price * current_volume
        vol_mult = round(current_volume / avg_vol_20d, 2) if avg_vol_20d > 0 else 0.0

        # Layer 1: Volume Filter (Spike or Contraction)
        is_potential_contraction = (active_context == ScanContext.END_MARKET and vol_mult <= 0.7)
        has_spike, _, spike_reason = check_volume_spike(
            current_volume=int(current_volume),
            avg_volume_20d=avg_vol_20d,
            current_turnover=turnover,
            multiplier_threshold=active_context.volume_threshold,
            min_turnover=config.risk.min_turnover,
            context=active_context,
        )
        if not has_spike and not is_potential_contraction:
            logger.debug(f"[{symbol}] Volume condition not met: {spike_reason}")
            return None

        # Layer 2: Technical Indicators & Setup
        df_indicators = calculate_indicators(df)
        setup_type, metrics = detect_technical_setup(
            df_indicators,
            vol_mult,
            context=active_context,
        )
        if setup_type is None:
            logger.debug(f"[{symbol}] No valid technical setup detected for context {active_context.value}")
            return None

        # ARA Proximity Safety Guard (FR-05 & §4.1)
        prev_close = float(df["close"].iloc[-2]) if len(df) >= 2 else current_price
        is_blocked_ara, ara_reason = is_near_ara(
            current_price=current_price,
            previous_close=prev_close,
            buffer_ticks=config.risk.ara_buffer_ticks,
            buffer_percent=config.risk.ara_buffer_percent,
        )
        if is_blocked_ara:
            logger.warning(f"[{symbol}] Signal aborted near ARA: {ara_reason}")
            return None

        # Risk Engine: Trading Plan (Entry, SL, TP1, TP2, RRR >= 2.0)
        atr_val = metrics.get("atr", current_price * 0.03)
        plan, plan_err = generate_trading_plan(
            current_price=current_price,
            atr=atr_val,
            atr_multiplier=config.risk.atr_sl_multiplier,
            min_rrr=config.risk.min_rrr,
            resistance_20d=metrics.get("resistance_20"),
        )
        if plan is None:
            logger.debug(f"[{symbol}] Trading plan rejected: {plan_err}")
            return None

        # Layer 3: Broker Flow (Bandarmologi) with contextual reference date
        ref_date = get_broker_reference_date(active_context, self.broker_fetcher.calendar)
        broker_summary = self.broker_fetcher.fetch_broker_summary(symbol, reference_date=ref_date)

        # AI Layer: Corporate Disclosure Sentiment
        disclosure_text = self.disclosure_fetcher.fetch_latest_disclosure(symbol)
        sentiment = self.sentiment_analyzer.analyze(symbol, disclosure_text)

        # Construct Validated Signal Payload
        signal = SignalPayload(
            ticker=symbol,
            company_name=ticker.company_name,
            setup_type=setup_type,
            parameters=plan,
            metrics=SignalMetrics(
                rsi=metrics.get("rsi", 50.0),
                volume_multiplier=vol_mult,
                foreign_accum_rank=broker_summary.foreign_accum_rank,
                broker_accum_rank=broker_summary.accum_rank,
            ),
            ai_context=sentiment.summary,
            scan_context=active_context.value,
            scan_date=ref_date,
        )

        # Dispatch via Telegram Notifier
        dispatched = self.notifier.dispatch_signal(signal, context=active_context)
        if dispatched:
            logger.info(f"Signal dispatched for {symbol} ({setup_type}) [{active_context.value}]")

        # Persist to Database or Flat Buffer
        self.db.log_signal(signal, sentiment_score=sentiment.sentiment_score)

        return signal

