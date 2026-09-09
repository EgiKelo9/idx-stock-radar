from typing import Optional
import json
import subprocess
import requests
from utils.logger import get_logger
from utils.retry import retry_sync

logger = get_logger("disclosure_fetcher")


class DisclosureFetcher:
    def __init__(self, max_words: int = 500):
        self.max_words = max_words
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.idx.co.id/",
        })

    def truncate_to_max_words(self, text: str) -> str:
        """Limits input to maximum words according to  6.2."""
        words = text.strip().split()
        if len(words) > self.max_words:
            return " ".join(words[: self.max_words]) + "..."
        return text

    def _fetch_url(self, url: str) -> Optional[dict]:
        """Attempts fetching JSON via requests, falling back to curl.exe if blocked by Cloudflare."""
        try:
            resp = self.session.get(url, timeout=8)
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 403:
                logger.debug(f"Direct request got 403, attempting curl.exe fallback for {url}")
        except Exception as e:
            logger.debug(f"Session get failed: {e}, trying curl.exe fallback")

        try:
            cmd = ["curl.exe", "-s", url, "-H", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"]
            res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=10)
            if res.returncode == 0 and res.stdout.strip().startswith("{"):
                return json.loads(res.stdout)
        except Exception as e:
            logger.warning(f"curl.exe fallback also failed: {e}")

        return None

    @retry_sync(max_attempts=3, delays=(2.0, 4.0, 8.0))
    def fetch_latest_disclosure(self, ticker: str) -> Optional[str]:
        """
        Fetches the latest official disclosure text for a given ticker using
        https://www.idx.co.id/primary/NewsAnnouncement/GetNewsSearch?pageNumber=1&pageSize=4&isHeadline=1&locale=id-id
        Returns cleaned text under max_words or None if unavailable.
        """
        clean_symbol = ticker.strip().upper().replace(".JK", "")

        # Try searching by ticker keyword first
        url = f"https://www.idx.co.id/primary/NewsAnnouncement/GetNewsSearch?pageNumber=1&pageSize=4&isHeadline=1&locale=id-id&keyword={clean_symbol}"
        data = self._fetch_url(url)

        items = []
        if data and isinstance(data, dict):
            items = data.get("Items", []) or data.get("items", []) or data.get("data", [])

        # If no specific ticker news found, fallback to general headline news
        if not items:
            general_url = "https://www.idx.co.id/primary/NewsAnnouncement/GetNewsSearch?pageNumber=1&pageSize=4&isHeadline=1&locale=id-id"
            data = self._fetch_url(general_url)
            if data and isinstance(data, dict):
                items = data.get("Items", []) or data.get("items", []) or data.get("data", [])

        if items:
            latest = items[0]
            title = latest.get("Title", "") or latest.get("JudulPengumuman", "") or ""
            summary = latest.get("Summary", "") or latest.get("Content", "") or latest.get("Deskripsi", "") or title
            tags = latest.get("Tags", "")
            tag_info = f" [Tag: {tags}]" if tags else ""

            full_text = f"Pengumuman: {title}. Detail: {summary}{tag_info}"
            return self.truncate_to_max_words(full_text)

        return None
