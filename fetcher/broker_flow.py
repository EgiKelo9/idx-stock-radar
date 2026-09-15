from datetime import datetime
from typing import Optional, List, Dict
import requests
from models.ticker import BrokerItem, BrokerSummary
from screener.broker_analysis import analyze_broker_flow
from utils.logger import get_logger
from utils.market_calendar import MarketCalendar
from utils.retry import retry_sync

logger = get_logger("broker_flow_fetcher")

# Known broker categories on IDX for bandarmologi classification
FOREIGN_BROKERS = {"AK", "BK", "CS", "KZ", "RX", "ZP", "CG", "AI", "AG", "MS", "DB", "ML", "TP", "GW"}
INSTITUTIONAL_BROKERS = FOREIGN_BROKERS | {"LG", "CC", "DX", "NI", "SQ", "OD"}
RETAIL_BROKERS = {"YP", "PD", "XC", "XL", "EP", "KK", "GR", "IH", "HD", "AZ", "MG"}


class BrokerFlowFetcher:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.idx.co.id/",
        })
        self.calendar = MarketCalendar()
        self._broker_cache: Dict[str, BrokerSummary] = {}

    def _determine_effective_date(
        self,
        target_date: Optional[str] = None,
        reference_date: Optional[str] = None,
    ) -> str:
        """
        Determines the appropriate date for broker summary fetching.
        Priority: reference_date > target_date > Smart off-hours logic (D-1 before 10:00 WIB or off-trading days).
        """
        if reference_date:
            return reference_date
        if target_date:
            return target_date

        now_wib = self.calendar.get_current_time()
        # IDX Broker summary is only available intraday after trading starts (~10:00 WIB).
        # Before 10:00 WIB or on weekends/holidays, use previous trading day (D-1 settled).
        if now_wib.hour < 10 or not self.calendar.is_trading_day(now_wib):
            prev_day = self.calendar.get_previous_trading_day(now_wib)
            return prev_day.strftime("%Y%m%d")

        return now_wib.strftime("%Y%m%d")

    def _query_idx_endpoint(self, clean_symbol: str, date_str: str) -> Optional[BrokerSummary]:
        """Queries IDX endpoint for a specific symbol and date."""
        try:
            url = f"https://www.idx.co.id/primary/TradingSummary/GetBrokerSummary?date={date_str}&stockCode={clean_symbol}"
            resp = self.session.get(url, timeout=8)
            if resp.status_code == 200:
                data = resp.json()

                # Format A: buyers/sellers already separated
                buyers_raw = data.get("Buyers", []) or (data.get("data", {}).get("Buyers", []) if isinstance(data.get("data"), dict) else [])
                sellers_raw = data.get("Sellers", []) or (data.get("data", {}).get("Sellers", []) if isinstance(data.get("data"), dict) else [])

                if buyers_raw and sellers_raw:
                    total_vol = sum(b.get("Volume", 0) for b in buyers_raw)
                    if total_vol > 0:
                        top_buyers = [
                            BrokerItem(
                                broker_code=b.get("BrokerCode") or b.get("IDFirm", "UNK"),
                                volume=int(b.get("Volume", 0)),
                                value=float(b.get("Value", 0.0)),
                            )
                            for b in buyers_raw[:5]
                        ]
                        top_sellers = [
                            BrokerItem(
                                broker_code=s.get("BrokerCode") or s.get("IDFirm", "UNK"),
                                volume=int(s.get("Volume", 0)),
                                value=float(s.get("Value", 0.0)),
                            )
                            for s in sellers_raw[:5]
                        ]
                        return analyze_broker_flow(
                            symbol=clean_symbol,
                            date_str=date_str,
                            total_volume=total_vol,
                            top_buyers=top_buyers,
                            top_sellers=top_sellers,
                        )

                # Format B: Official IDX GetBrokerSummary response (flat list of broker records under 'data')
                raw_list = data.get("data", []) if isinstance(data.get("data"), list) else []
                if raw_list:
                    broker_items = []
                    for item in raw_list:
                        firm = item.get("IDFirm") or item.get("BrokerCode") or ""
                        vol = int(item.get("Volume", 0))
                        val = float(item.get("Value", 0.0))
                        if firm and vol > 0:
                            broker_items.append(BrokerItem(broker_code=firm, volume=vol, value=val))

                    if broker_items:
                        total_vol = sum(b.volume for b in broker_items)
                        if total_vol > 0:
                            sorted_brokers = sorted(broker_items, key=lambda b: b.volume, reverse=True)

                            inst_brokers = [b for b in sorted_brokers if b.broker_code in INSTITUTIONAL_BROKERS]
                            retail_brokers = [b for b in sorted_brokers if b.broker_code in RETAIL_BROKERS]

                            if inst_brokers and retail_brokers:
                                top_buyers = inst_brokers[:5]
                                top_sellers = retail_brokers[:5]
                            else:
                                top_buyers = sorted_brokers[:3]
                                top_sellers = sorted_brokers[3:6] if len(sorted_brokers) > 3 else []

                            # Foreign flow estimation based on foreign vs retail transaction value
                            foreign_val = sum(b.value for b in sorted_brokers if b.broker_code in FOREIGN_BROKERS)
                            retail_val = sum(b.value for b in sorted_brokers if b.broker_code in RETAIL_BROKERS)
                            est_foreign_net = foreign_val - retail_val

                            return analyze_broker_flow(
                                symbol=clean_symbol,
                                date_str=date_str,
                                total_volume=total_vol,
                                top_buyers=top_buyers,
                                top_sellers=top_sellers,
                                foreign_net_buy=est_foreign_net,
                            )
        except Exception as e:
            logger.warning(f"Direct IDX broker summary failed for {clean_symbol} on {date_str}: {e}")

        # Attempt 2: idx-bei library if installed
        try:
            import idx_bei
            summary = idx_bei.get_broker_summary(clean_symbol, date=date_str)
            if summary and int(summary.get("total_volume", 0)) > 0:
                return analyze_broker_flow(
                    symbol=clean_symbol,
                    date_str=date_str,
                    total_volume=int(summary.get("total_volume", 1)),
                    top_buyers=[],
                    top_sellers=[],
                )
        except (ImportError, Exception):
            pass

        return None

    @retry_sync(max_attempts=3, delays=(2.0, 4.0, 8.0))
    def fetch_broker_summary(
        self,
        symbol: str,
        target_date: Optional[str] = None,
        reference_date: Optional[str] = None,
    ) -> BrokerSummary:
        """
        Fetches daily broker summary for a given symbol.
        target_date / reference_date format: YYYYMMDD or None for smart date resolution.
        """
        clean_symbol = symbol.upper().replace(".JK", "")
        effective_date = self._determine_effective_date(target_date, reference_date)

        # Check in-memory cache to prevent hundreds of duplicate HTTP requests
        cache_key = f"{clean_symbol}_{effective_date}"
        if cache_key in self._broker_cache:
            return self._broker_cache[cache_key]

        # 1. Attempt primary effective date
        summary = self._query_idx_endpoint(clean_symbol, effective_date)

        # 2. If primary was today and returned empty/failed, attempt fallback to D-1
        now_wib = self.calendar.get_current_time()
        today_str = now_wib.strftime("%Y%m%d")
        if summary is None and effective_date == today_str:
            prev_trading_str = self.calendar.get_previous_trading_day(now_wib).strftime("%Y%m%d")
            logger.debug(f"Broker data for {clean_symbol} on {today_str} not available; falling back to D-1 ({prev_trading_str})")
            summary = self._query_idx_endpoint(clean_symbol, prev_trading_str)
            if summary is not None:
                self._broker_cache[cache_key] = summary
                return summary

        # 3. If still no data available, return transparent DATA_N/A baseline
        if summary is None:
            logger.info(f"Broker flow data unavailable for {clean_symbol} on {effective_date}, marking DATA_N/A")
            summary = BrokerSummary(
                symbol=clean_symbol,
                date=effective_date,
                total_volume=0,
                top3_buyers=[],
                top3_sellers=[],
                top3_net_buy_volume=0,
                top3_accumulation_ratio=0.0,
                accum_rank="DATA_N/A",
                foreign_accum_rank="DATA_N/A",
            )

        self._broker_cache[cache_key] = summary
        return summary
