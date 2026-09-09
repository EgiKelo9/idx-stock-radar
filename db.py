import json
from pathlib import Path
from typing import Optional, List
from config import config
from models.signal import SignalPayload
from models.ticker import Ticker
from utils.logger import get_logger

logger = get_logger("database_manager")

BUFFER_FILE = Path(__file__).resolve().parent / "signal_buffer.json"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS master_tickers (
    symbol VARCHAR(10) PRIMARY KEY,
    company_name VARCHAR(255) NOT NULL,
    board VARCHAR(50) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    last_updated TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS market_data (
    time TIMESTAMPTZ NOT NULL,
    symbol VARCHAR(10) REFERENCES master_tickers(symbol),
    open NUMERIC(10, 2) NOT NULL,
    high NUMERIC(10, 2) NOT NULL,
    low NUMERIC(10, 2) NOT NULL,
    close NUMERIC(10, 2) NOT NULL,
    volume BIGINT NOT NULL,
    turnover NUMERIC(18, 2) NOT NULL,
    PRIMARY KEY (time, symbol)
);

CREATE TABLE IF NOT EXISTS signal_logs (
    id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    symbol VARCHAR(10),
    entry_price NUMERIC(10, 2) NOT NULL,
    stop_loss NUMERIC(10, 2) NOT NULL,
    take_profit_1 NUMERIC(10, 2) NOT NULL,
    take_profit_2 NUMERIC(10, 2) NOT NULL,
    risk_reward_ratio NUMERIC(4, 2) NOT NULL,
    volume_ratio NUMERIC(4, 2) NOT NULL,
    sentiment_score NUMERIC(3, 2),
    sentiment_summary TEXT,
    execution_status VARCHAR(20) DEFAULT 'SENT'
);
"""


class DatabaseManager:
    def __init__(self):
        self.db_cfg = config.database
        self._pool = None

    def _get_connection(self):
        try:
            import psycopg2
            return psycopg2.connect(
                host=self.db_cfg.host,
                port=self.db_cfg.port,
                dbname=self.db_cfg.name,
                user=self.db_cfg.user,
                password=self.db_cfg.password,
                connect_timeout=3,
            )
        except Exception:
            return None

    def initialize_schema(self) -> bool:
        """Initializes tables and hypertable if PostgreSQL is accessible."""
        conn = self._get_connection()
        if conn is None:
            logger.warning("PostgreSQL offline; database buffering will be active.")
            return False

        try:
            with conn.cursor() as cur:
                cur.execute(SCHEMA_SQL)
                # Attempt to create Timescale hypertable
                try:
                    cur.execute("SELECT create_hypertable('market_data', 'time', if_not_exists => TRUE);")
                except Exception:
                    pass  # Non-timescaledb postgres compatibility
            conn.commit()
            conn.close()
            logger.info("Database schema initialized successfully.")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize schema: {e}")
            if conn:
                conn.close()
            return False

    def log_signal(self, signal: SignalPayload, sentiment_score: Optional[float] = None) -> bool:
        """
        Records signal to signal_logs table, or appends to local buffer if DB is down (§6.2).
        """
        conn = self._get_connection()
        if conn is not None:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO signal_logs (
                            id, symbol, entry_price, stop_loss,
                            take_profit_1, take_profit_2, risk_reward_ratio,
                            volume_ratio, sentiment_score, sentiment_summary, execution_status
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            signal.signal_id,
                            signal.ticker,
                            signal.parameters.entry,
                            signal.parameters.stop_loss,
                            signal.parameters.take_profit_1,
                            signal.parameters.take_profit_2,
                            signal.parameters.rrr,
                            signal.metrics.volume_multiplier,
                            sentiment_score,
                            signal.ai_context,
                            "SENT",
                        ),
                    )
                conn.commit()
                conn.close()
                return True
            except Exception as e:
                logger.error(f"Failed to write signal to DB: {e}. Falling back to flat-file buffer.")
                if conn:
                    conn.close()

        # Fallback flat file buffering (§6.2)
        try:
            entries = []
            if BUFFER_FILE.exists():
                with open(BUFFER_FILE, "r", encoding="utf-8") as f:
                    entries = json.load(f)
            entries.append(signal.model_dump())
            with open(BUFFER_FILE, "w", encoding="utf-8") as f:
                json.dump(entries, f, indent=2)
            logger.info(f"Signal {signal.signal_id} buffered to {BUFFER_FILE}")
            return True
        except Exception as buffer_err:
            logger.error(f"Failed to buffer signal to flat file: {buffer_err}")
            return False
