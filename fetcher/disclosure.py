from typing import Optional
import json
import shutil
import subprocess
import urllib.request
import xml.etree.ElementTree as ET
import requests
from utils.logger import get_logger
from utils.retry import retry_sync

logger = get_logger("disclosure_fetcher")


class DisclosureFetcher:
    def __init__(self, max_words: int = 500):
        self.max_words = max_words
        self.session = requests.Session()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.idx.co.id/id/berita/pengumuman/",
        }
        self.session.headers.update(self.headers)

    def truncate_to_max_words(self, text: str) -> str:
        """Limits input to maximum words according to  6.2."""
        words = text.strip().split()
        if len(words) > self.max_words:
            return " ".join(words[: self.max_words]) + "..."
        return text

    def _fetch_url(self, url: str) -> Optional[dict]:
        """
        Attempts fetching JSON via curl_cffi (browser TLS impersonation to bypass Cloudflare WAF),
        with fallback to requests and system curl.
        """
        # Tier 1: curl_cffi with Chrome impersonation (bypasses Cloudflare JA3 / WAF)
        try:
            from curl_cffi import requests as cffi_requests
            resp = cffi_requests.get(url, headers=self.headers, impersonate="chrome120", timeout=10)
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 403:
                logger.debug(f"curl_cffi received 403 for {url}")
        except Exception as e:
            logger.debug(f"curl_cffi fetch failed for {url}: {e}")

        # Tier 2: Standard requests.Session
        try:
            resp = self.session.get(url, timeout=8)
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 403:
                logger.debug(f"Direct request got 403, attempting curl CLI fallback for {url}")
        except Exception as e:
            logger.debug(f"Session get failed: {e}, trying curl CLI fallback")

        # Tier 3: Subprocess curl CLI
        curl_bin = shutil.which("curl") or shutil.which("curl.exe")
        if not curl_bin:
            logger.debug("curl binary not found on system; skipping curl fallback.")
            return None

        try:
            cmd = [curl_bin, "-s", url, "-H", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"]
            res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=10)
            if res.returncode == 0 and res.stdout.strip().startswith("{"):
                return json.loads(res.stdout)
        except Exception as e:
            logger.warning(f"curl fallback also failed: {e}")

        return None

    def _fetch_google_news_rss(self, clean_symbol: str) -> Optional[str]:
        """
        Fetches fresh financial news headlines via Google News RSS for Indonesian markets.
        Resilient alternative when IDX disclosure has no material action today.
        """
        url = f"https://news.google.com/rss/search?q={clean_symbol}+saham&hl=id&gl=ID&ceid=ID:id"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        try:
            with urllib.request.urlopen(req, timeout=6) as resp:
                tree = ET.fromstring(resp.read())
                items = tree.findall(".//item")
                if not items:
                    return None

                snippets = []
                for it in items[:3]:
                    t = it.find("title")
                    title = t.text if t is not None and t.text else ""
                    d = it.find("pubDate")
                    pdate = f" ({d.text[:16]})" if d is not None and d.text else ""
                    if title:
                        clean_title = "".join(c for c in title if ord(c) < 10000).strip()
                        snippets.append(f"{clean_title}{pdate}")

                if snippets:
                    full_text = f"Kompilasi Berita Finansial Terkini {clean_symbol}: " + " | ".join(snippets)
                    return self.truncate_to_max_words(full_text)
        except Exception as e:
            logger.debug(f"Google News RSS fetch failed for {clean_symbol}: {e}")

        return None

    @retry_sync(max_attempts=3, delays=(2.0, 4.0, 8.0))
    def fetch_latest_disclosure(self, ticker: str) -> Optional[str]:
        """
        Fetches the latest official disclosure or verified news for a given ticker.
        Multi-tier resolution:
        1. Ticker-specific disclosure from IDX (NewsAnnouncement/GetNewsSearch?keyword=...)
        2. Financial news RSS from trusted Indonesian media (Google News Financial Feed)
        3. General IDX headline announcement
        """
        clean_symbol = ticker.strip().upper().replace(".JK", "")

        # Tier 1: IDX official disclosure by ticker keyword
        url = f"https://www.idx.co.id/primary/NewsAnnouncement/GetNewsSearch?pageNumber=1&pageSize=4&isHeadline=1&locale=id-id&keyword={clean_symbol}"
        data = self._fetch_url(url)

        items = []
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

        # Tier 2: Google News Financial RSS for Indonesian market media (Kontan, Bisnis, CNBC, dll.)
        rss_news = self._fetch_google_news_rss(clean_symbol)
        if rss_news:
            return rss_news

        # Tier 3: General headline news from IDX
        general_url = "https://www.idx.co.id/primary/NewsAnnouncement/GetNewsSearch?pageNumber=1&pageSize=4&isHeadline=1&locale=id-id"
        general_data = self._fetch_url(general_url)
        if general_data and isinstance(general_data, dict):
            gen_items = general_data.get("Items", []) or general_data.get("items", []) or general_data.get("data", [])
            if gen_items:
                latest = gen_items[0]
                title = latest.get("Title", "") or latest.get("JudulPengumuman", "") or ""
                summary = latest.get("Summary", "") or latest.get("Content", "") or latest.get("Deskripsi", "") or title
                tags = latest.get("Tags", "")
                tag_info = f" [Tag: {tags}]" if tags else ""
                full_text = f"Pengumuman: {title}. Detail: {summary}{tag_info}"
                return self.truncate_to_max_words(full_text)

        return None
