from typing import List, Optional, Set
import time
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
from screener.confidence_scorer import calculate_confidence_score
from screener.data_quality import validate_candle_data
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
        self._sent_today_cache: Set[str] = set()

    def evaluate_ticker(
        self,
        ticker: Ticker,
        context: Optional[ScanContext] = None,
        market_regime: str = "NORMAL",
    ) -> Optional[SignalPayload]:
        """
        Executes multi-layer screening, data quality validation, risk assessment,
        and confidence scoring for a single ticker (Stages 5 - 17).
        Returns evaluated SignalPayload candidate or None.
        """
        active_context = context or ScanContext.MID_DAY
        symbol = ticker.clean_symbol

        # Stage 5: Eligibility Filter
        is_eligible, elig_reason = check_ticker_eligibility(ticker)
        if not is_eligible:
            logger.debug(f"[{symbol}] Ineligible: {elig_reason}")
            return None

        # Stage 7: Market Data Snapshot
        snapshot = self.market_fetcher.get_market_snapshot(symbol)
        if snapshot is None:
            logger.debug(f"[{symbol}] Failed to retrieve market data")
            return None

        df, current_price, current_volume, avg_vol_20d = snapshot

        # Stage 6: Data Quality Gate
        is_valid_data, dq_reason = validate_candle_data(df, min_bars=20)
        if not is_valid_data:
            logger.debug(f"[{symbol}] Data Quality Gate rejected: {dq_reason}")
            return None

        turnover = current_price * current_volume
        vol_mult = round(current_volume / avg_vol_20d, 2) if avg_vol_20d > 0 else 0.0

        # Stage 8: Liquidity / Volume Condition
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

        # Stage 9: Indicator Calculation
        df_indicators = calculate_indicators(df)

        # Stage 10 & 11: Setup Detection & Technical Confirmation
        setup_type, metrics = detect_technical_setup(
            df_indicators,
            vol_mult,
            context=active_context,
        )
        if setup_type is None:
            logger.debug(f"[{symbol}] No valid technical setup detected for context {active_context.value}")
            return None

        # Stage 12: ARA Proximity Safety Guard
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

        # Stage 13: Risk Engine & Trading Plan
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

        # Stage 14: Broker Flow (Bandarmologi)
        ref_date = get_broker_reference_date(active_context, self.broker_fetcher.calendar)
        broker_summary = self.broker_fetcher.fetch_broker_summary(symbol, reference_date=ref_date)

        # Stage 15 & 16: News Disclosure & AI Sentiment
        disclosure_text = self.disclosure_fetcher.fetch_latest_disclosure(symbol)
        sentiment = self.sentiment_analyzer.analyze(symbol, disclosure_text)

        # Stage 17: Confidence Scoring
        confidence = calculate_confidence_score(
            setup_type=setup_type,
            volume_multiplier=vol_mult,
            rsi=metrics.get("rsi", 50.0),
            broker_summary=broker_summary,
            sentiment=sentiment,
            trading_plan=plan,
            market_regime=market_regime,
        )

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
            confidence_score=confidence,
            market_regime=market_regime,
            status="PENDING",
        )

        logger.info(
            f"[{symbol}] Candidate evaluated: {setup_type} | Confidence: {confidence:.1f}/100 | "
            f"RRR: 1:{plan.rrr:.1f} | Broker: {broker_summary.accum_rank}"
        )
        return signal

    def process_ticker(
        self,
        ticker: Ticker,
        context: Optional[ScanContext] = None,
        market_regime: Optional[str] = None,
    ) -> Optional[SignalPayload]:
        """
        Single-ticker evaluation hook.
        Maintains backward compatibility with unit tests and legacy single execution.
        """
        regime = market_regime or getattr(self, "active_regime", "NORMAL")
        return self.evaluate_ticker(ticker, context=context, market_regime=regime)

    def rank_and_dispatch(
        self,
        candidates: List[SignalPayload],
        context: Optional[ScanContext] = None,
        top_n: int = 5,
    ) -> List[SignalPayload]:
        """
        Stages 19 - 25:
        Global Ranking, Deduplication, Top-N Selection, DB persistence, and Telegram dispatch.
        """
        active_context = context or ScanContext.MID_DAY
        if not candidates:
            logger.info(f"No candidates to rank or dispatch for {active_context.value}.")
            return []

        # Stage 19: Global Ranking (Highest Confidence Score first, then Highest RRR)
        ranked = sorted(
            candidates,
            key=lambda s: (s.confidence_score, s.parameters.rrr),
            reverse=True,
        )

        # Stage 20: Deduplication (Unique ticker per day / scan cycle)
        unique_candidates: List[SignalPayload] = []
        seen_symbols: Set[str] = set()
        for cand in ranked:
            dedup_key = f"{cand.ticker}_{cand.scan_date}_{cand.scan_context}"
            if cand.ticker not in seen_symbols and dedup_key not in self._sent_today_cache:
                unique_candidates.append(cand)
                seen_symbols.add(cand.ticker)

        # Stage 21: Top-N Selection
        top_selected = unique_candidates[:top_n]
        logger.info(
            f"Global Ranking selected Top {len(top_selected)} of {len(candidates)} candidates "
            f"for {active_context.value} dispatch (Top Score: {top_selected[0].confidence_score:.1f} / 100)"
        )

        dispatched_list: List[SignalPayload] = []
        for signal in top_selected:
            # Stage 22: Persist PENDING
            signal.status = "PENDING"
            self.db.log_signal(signal, status="PENDING")

            # Stage 23: Telegram Signal Dispatch
            try:
                time.sleep(1.0)  # Rate pacing for Telegram API
                sent_ok = self.notifier.dispatch_signal(signal, context=active_context)
                if sent_ok:
                    # Stage 24: Mark SENT
                    signal.status = "SENT"
                    self.db.log_signal(signal, status="SENT")
                    dedup_key = f"{signal.ticker}_{signal.scan_date}_{signal.scan_context}"
                    self._sent_today_cache.add(dedup_key)
                    dispatched_list.append(signal)
                    logger.info(
                        f"Signal dispatched successfully: {signal.ticker} ({signal.setup_type}) "
                        f"[Confidence {signal.confidence_score:.1f}] [{active_context.value}]"
                    )
                else:
                    # Stage 24: Mark FAILED
                    signal.status = "FAILED"
                    self.db.log_signal(signal, status="FAILED")
                    logger.warning(f"Telegram dispatch failed for {signal.ticker}")
            except Exception as e:
                signal.status = "FAILED"
                self.db.log_signal(signal, status="FAILED")
                logger.error(f"Error dispatching signal for {signal.ticker}: {e}")

        # Stage 25: Post-Signal Monitoring summary
        logger.info(
            f"Post-Signal Cycle Summary [{active_context.value}]: "
            f"{len(dispatched_list)} / {len(top_selected)} signals successfully notified."
        )
        return dispatched_list
