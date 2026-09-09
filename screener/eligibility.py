from typing import Tuple
from models.ticker import Ticker
from config import config


def check_ticker_eligibility(ticker: Ticker) -> Tuple[bool, str]:
    """
    Evaluates ticker against hard elimination filters.
    Returns: (is_eligible: bool, reason: str)
    """
    # Filter 1: FCA Board check
    if ticker.board.upper() == "FCA":
        return False, f"Ticker {ticker.clean_symbol} is in Papan Pemantauan Khusus (FCA)"

    # Filter 2: Suspension flag check
    if ticker.is_suspended:
        return False, f"Ticker {ticker.clean_symbol} is currently suspended"

    # Filter 3: Minimum 20-day turnover (FR-02)
    min_turnover = config.risk.min_turnover
    if ticker.avg_turnover_20d < min_turnover:
        return False, (
            f"Ticker {ticker.clean_symbol} 20-day average turnover (Rp{ticker.avg_turnover_20d:,.0f}) "
            f"is below threshold (Rp{min_turnover:,.0f})"
        )

    return True, ""
