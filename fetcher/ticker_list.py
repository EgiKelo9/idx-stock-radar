from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import List, Optional, Set
import requests
from config import config
from models.ticker import BoardType, Ticker
from utils.logger import get_logger

logger = get_logger("ticker_list_fetcher")

# Local cache file path (repository root)
LOCAL_CACHE_PATH = Path(__file__).resolve().parent.parent / "ticker_list_response.txt"


class TickerListFetcher:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.idx.co.id/",
        })
        self._cached_tickers: List[Ticker] = []
        self._last_fetch_time: Optional[datetime] = None

    def _normalize_board(self, board_str: str) -> BoardType:
        """Maps IDX board name to standardized BoardType literal."""
        raw = (board_str or "").strip().upper()
        if "PEMANTAUAN" in raw or "KHUSUS" in raw or "FCA" in raw:
            return "FCA"
        elif "PENGEMBANGAN" in raw:
            return "PENGEMBANGAN"
        elif "AKSELERASI" in raw:
            return "AKSELERASI"
        elif "UTAMA" in raw or "EKONOMI BARU" in raw:
            return "UTAMA"
        return "UNKNOWN"

    def _parse_ticker_data(self, data: dict, allowed_boards: Optional[Set[str]] = None) -> List[Ticker]:
        """Parses company profile items from IDX JSON response into Ticker models."""
        profiles = data.get("data", []) or data.get("profiles", [])
        if not isinstance(profiles, list):
            return []

        tickers: List[Ticker] = []
        for p in profiles:
            code = (p.get("KodeEmiten") or p.get("StockCode") or "").strip().upper()
            if not code:
                continue

            # Exclude non-stock instruments (ETF, Obligasi, SPEI, EBA) if flag is present
            is_saham = p.get("EfekEmiten_Saham")
            if is_saham is False:
                continue

            # Check status (0 = Active)
            status = p.get("Status", 0)
            is_active = (status == 0)

            name = (p.get("NamaEmiten") or p.get("CompanyName") or f"Emiten {code}").strip()
            board = self._normalize_board(p.get("PapanPencatatan", "Utama"))

            # Board filter check
            if allowed_boards and "ALL" not in allowed_boards and board not in allowed_boards:
                continue

            tickers.append(
                Ticker(
                    symbol=code,
                    company_name=name,
                    board=board,
                    is_active=is_active,
                    avg_turnover_20d=2_000_000_000.0,
                )
            )

        return tickers

    def _fetch_from_network(self) -> Optional[dict]:
        """Fetches ticker universe from IDX using DataTables pagination (start=0&length=1500)."""
        url = "https://www.idx.co.id/primary/ListedCompany/GetCompanyProfiles?start=0&length=1500"

        # Attempt 1: requests session
        try:
            resp = self.session.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data and (data.get("data") or data.get("profiles")):
                    return data
            elif resp.status_code == 403:
                logger.debug("Direct request got 403, attempting curl fallback for ticker list")
        except Exception as e:
            logger.debug(f"Direct ticker request failed: {e}, attempting curl fallback")

        # Attempt 2: curl fallback (cross-platform)
        curl_bin = shutil.which("curl") or shutil.which("curl.exe")
        if not curl_bin:
            logger.debug("curl binary not found on system; skipping curl fallback.")
            return None

        try:
            cmd = [
                curl_bin,
                "-s",
                url,
                "-H", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
                "-H", "Accept: application/json, text/plain, */*",
                "-H", "Referer: https://www.idx.co.id/id/perusahaan-tercatat/profil-perusahaan-tercatat",
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=15)
            if res.returncode == 0 and res.stdout.strip().startswith("{"):
                return json.loads(res.stdout)
        except Exception as e:
            logger.warning(f"curl ticker list fetch failed: {e}")

        return None

    def fetch_listed_tickers(self, force_refresh: bool = False) -> List[Ticker]:
        """
        Retrieves the complete universe of IDX listed companies (+900 emiten).
        Implements in-memory TTL caching, live network fetching, and local snapshot fallback.
        """
        # 1. In-memory TTL cache check
        ttl_hours = config.system.ticker_cache_ttl_hours
        now = datetime.now()
        if not force_refresh and self._cached_tickers and self._last_fetch_time:
            if now - self._last_fetch_time < timedelta(hours=ttl_hours):
                logger.debug(f"Serving {len(self._cached_tickers)} tickers from in-memory cache")
                return self._cached_tickers

        board_config = os.getenv("TICKER_BOARDS", config.system.ticker_boards)
        allowed_boards = {b.strip().upper() for b in board_config.split(",") if b.strip()}

        # 2. Live network fetch
        network_data = self._fetch_from_network()
        if network_data:
            parsed = self._parse_ticker_data(network_data, allowed_boards)
            if len(parsed) > 50:
                self._cached_tickers = parsed
                self._last_fetch_time = now
                logger.info(f"Loaded {len(parsed)} tickers live from IDX API")
                # Persist snapshot locally for offline/fallback stability
                try:
                    with open(LOCAL_CACHE_PATH, "w", encoding="utf-8") as f:
                        json.dump(network_data, f)
                except Exception as e:
                    logger.debug(f"Could not persist ticker snapshot locally: {e}")
                return parsed

        # 3. Local file cache fallback (ticker_list_response.txt)
        if LOCAL_CACHE_PATH.exists():
            try:
                with open(LOCAL_CACHE_PATH, "r", encoding="utf-8") as f:
                    local_data = json.load(f)
                parsed = self._parse_ticker_data(local_data, allowed_boards)
                if parsed:
                    logger.info(f"Loaded {len(parsed)} tickers from local fallback cache ({LOCAL_CACHE_PATH.name})")
                    self._cached_tickers = parsed
                    self._last_fetch_time = now
                    return parsed
            except Exception as e:
                logger.warning(f"Failed to load tickers from local cache: {e}")

        # 4. In-memory cached data as last resort
        if self._cached_tickers:
            return self._cached_tickers

        logger.error("All ticker sources failed, returning empty list")
        return []
