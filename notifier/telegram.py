from typing import Optional
import httpx
from config import config
from models.signal import SignalPayload
from notifier.formatter import format_signal_message
from utils.logger import get_logger
from utils.retry import retry_sync

logger = get_logger("telegram_notifier")


class TelegramNotifier:
    def __init__(
        self,
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None,
    ):
        self.bot_token = bot_token or config.telegram.bot_token
        self.chat_id = chat_id or config.telegram.chat_id
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"

    @property
    def is_configured(self) -> bool:
        return bool(
            self.bot_token
            and not self.bot_token.startswith("your_")
            and self.chat_id
            and not self.chat_id.startswith("your_")
        )

    @retry_sync(max_attempts=3, delays=(2.0, 4.0, 8.0))
    def send_message(self, text: str, parse_mode: str = "Markdown") -> bool:
        """
        Sends raw text message to configured Telegram chat/channel.
        """
        if not self.is_configured:
            logger.info("Telegram Bot Token or Chat ID not configured. Message logged to console instead.")
            import sys
            encoded = text.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(sys.stdout.encoding or "utf-8")
            print("\n" + "=" * 50)
            print("SIMULATED TELEGRAM DISPATCH:")
            print(encoded)
            print("=" * 50 + "\n")
            return True

        url = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }

        with httpx.Client(timeout=10.0) as client:
            resp = client.post(url, json=payload)
            if resp.status_code == 200:
                logger.info("Telegram notification successfully dispatched.")
                return True
            else:
                logger.error(f"Telegram dispatch failed {resp.status_code}: {resp.text}")
                # Retry without markdown if parsing failed
                if "can't parse entities" in resp.text:
                    payload.pop("parse_mode", None)
                    retry_resp = client.post(url, json=payload)
                    return retry_resp.status_code == 200
                return False

    def dispatch_signal(self, signal: SignalPayload) -> bool:
        """
        Formats and sends a complete trading signal.
        """
        formatted = format_signal_message(signal)
        return self.send_message(formatted, parse_mode="Markdown")
