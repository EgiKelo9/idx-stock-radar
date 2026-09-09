from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Literal

# Load .env if present
BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"

try:
    from dotenv import load_dotenv
    if ENV_FILE.exists():
        load_dotenv(dotenv_path=ENV_FILE)
except ImportError:
    # Minimal fallback parser if python-dotenv is not yet installed
    if ENV_FILE.exists():
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip()
                    if k not in os.environ:
                        os.environ[k] = v.strip("'\"")


def get_env_bool(key: str, default: bool) -> bool:
    val = os.getenv(key)
    if val is None:
        return default
    return val.strip().lower() in ("true", "1", "t", "yes", "y")


def get_env_int(key: str, default: int) -> int:
    val = os.getenv(key)
    if val is None:
        return default
    try:
        return int(val.strip())
    except ValueError:
        return default


def get_env_float(key: str, default: float) -> float:
    val = os.getenv(key)
    if val is None:
        return default
    try:
        return float(val.strip())
    except ValueError:
        return default


@dataclass(frozen=True)
class TelegramSettings:
    bot_token: str = field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", ""))
    chat_id: str = field(default_factory=lambda: os.getenv("TELEGRAM_CHAT_ID", ""))

    def validate(self) -> None:
        if not self.bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN must be configured in .env or environment")
        if not self.chat_id:
            raise ValueError("TELEGRAM_CHAT_ID must be configured in .env or environment")


@dataclass(frozen=True)
class DatabaseSettings:
    host: str = field(default_factory=lambda: os.getenv("DB_HOST", "localhost"))
    port: int = field(default_factory=lambda: get_env_int("DB_PORT", 5432))
    name: str = field(default_factory=lambda: os.getenv("DB_NAME", "idx_market_db"))
    user: str = field(default_factory=lambda: os.getenv("DB_USER", "postgres"))
    password: str = field(default_factory=lambda: os.getenv("DB_PASSWORD", "idxpassword"))

    @property
    def connection_url(self) -> str:
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"

    @property
    def async_connection_url(self) -> str:
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"


@dataclass(frozen=True)
class LLMSettings:
    provider: Literal["openai", "anthropic", "openrouter"] = field(
        default_factory=lambda: os.getenv("LLM_PROVIDER", "openrouter").lower()  # type: ignore
    )
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    openrouter_api_key: str = field(default_factory=lambda: os.getenv("OPENROUTER_API_KEY", ""))
    model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "nvidia/nemotron-3-super-120b-a12b:free"))
    timeout_seconds: int = field(default_factory=lambda: get_env_int("LLM_TIMEOUT_SECONDS", 10))
    max_words: int = field(default_factory=lambda: get_env_int("LLM_MAX_WORDS", 500))


@dataclass(frozen=True)
class RiskSettings:
    min_turnover: float = field(default_factory=lambda: get_env_float("MIN_TURNOVER", 1_000_000_000.0))
    volume_spike_threshold: float = field(default_factory=lambda: get_env_float("VOLUME_SPIKE_THRESHOLD", 1.5))
    volume_avg_days: int = field(default_factory=lambda: get_env_int("VOLUME_AVG_DAYS", 20))
    atr_sl_multiplier: float = field(default_factory=lambda: get_env_float("ATR_SL_MULTIPLIER", 1.5))
    min_rrr: float = field(default_factory=lambda: get_env_float("MIN_RRR", 2.0))
    ara_buffer_percent: float = field(default_factory=lambda: get_env_float("ARA_BUFFER_PERCENT", 1.5))
    ara_buffer_ticks: int = field(default_factory=lambda: get_env_int("ARA_BUFFER_TICKS", 2))


@dataclass(frozen=True)
class TechnicalSettings:
    rsi_period: int = field(default_factory=lambda: get_env_int("RSI_PERIOD", 14))
    atr_period: int = field(default_factory=lambda: get_env_int("ATR_PERIOD", 14))
    sma_fast: int = field(default_factory=lambda: get_env_int("SMA_FAST", 20))
    sma_mid: int = field(default_factory=lambda: get_env_int("SMA_MID", 50))
    sma_slow: int = field(default_factory=lambda: get_env_int("SMA_SLOW", 200))


@dataclass(frozen=True)
class SystemSettings:
    scan_interval_minutes: int = field(default_factory=lambda: get_env_int("SCAN_INTERVAL_MINUTES", 15))
    timezone: str = field(default_factory=lambda: os.getenv("TZ", "Asia/Jakarta"))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO").upper())
    ticker_boards: str = field(default_factory=lambda: os.getenv("TICKER_BOARDS", "UTAMA,PENGEMBANGAN"))
    ticker_cache_ttl_hours: int = field(default_factory=lambda: get_env_int("TICKER_CACHE_TTL_HOURS", 6))


@dataclass(frozen=True)
class AppConfig:
    telegram: TelegramSettings = field(default_factory=TelegramSettings)
    database: DatabaseSettings = field(default_factory=DatabaseSettings)
    llm: LLMSettings = field(default_factory=LLMSettings)
    risk: RiskSettings = field(default_factory=RiskSettings)
    technical: TechnicalSettings = field(default_factory=TechnicalSettings)
    system: SystemSettings = field(default_factory=SystemSettings)


# Singleton instance
config = AppConfig()
