from datetime import datetime
from typing import Optional, List
import requests
from models.ticker import BrokerItem, BrokerSummary
from screener.broker_analysis import analyze_broker_flow
from utils.logger import get_logger
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

    @retry_sync(max_attempts=3, delays=(2.0, 4.0, 8.0))
    def fetch_broker_summary(
        self,
        symbol: str,
        target_date: Optional[str] = None,
    ) -> BrokerSummary:
        """
        Fetches daily broker summary for a given symbol.
        target_date format: YYYYMMDD or None for current day.
        """
        clean_symbol = symbol.upper().replace(".JK", "")
        if target_date is None:
            target_date = datetime.now().strftime("%Y%m%d")

        # Attempt 1: Direct IDX Broker Summary endpoint
        try:
            url = f"https://www.idx.co.id/primary/TradingSummary/GetBrokerSummary?date={target_date}&stockCode={clean_symbol}"
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
                            date_str=target_date,
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
                            date_str=target_date,
                            total_volume=total_vol,
                            top_buyers=top_buyers,
                            top_sellers=top_sellers,
                            foreign_net_buy=est_foreign_net,
                        )
        except Exception as e:
            logger.warning(f"Direct IDX broker summary failed for {clean_symbol}: {e}")

        # Attempt 2: idx-bei library if installed
        try:
            import idx_bei
            summary = idx_bei.get_broker_summary(clean_symbol, date=target_date)
            if summary:
                # Process idx_bei dataframe/dict
                return analyze_broker_flow(
                    symbol=clean_symbol,
                    date_str=target_date,
                    total_volume=int(summary.get("total_volume", 1)),
                    top_buyers=[],
                    top_sellers=[],
                )
        except (ImportError, Exception):
            pass

        # Fallback: Return neutral baseline if live feed is unavailable during intraday
        logger.info(f"Broker flow defaulting to NEUTRAL baseline for {clean_symbol}")
        return BrokerSummary(
            symbol=clean_symbol,
            date=target_date,
            total_volume=1,
            top3_buyers=[],
            top3_sellers=[],
            top3_net_buy_volume=0,
            top3_accumulation_ratio=0.0,
            accum_rank="NEUTRAL",
            foreign_accum_rank="NEUTRAL",
        )
