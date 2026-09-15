from typing import Optional, Tuple
from config import config
from models.scan_context import ScanContext


def check_volume_spike(
    current_volume: int,
    avg_volume_20d: float,
    current_turnover: float,
    multiplier_threshold: float = 1.5,
    min_turnover: float = 1_000_000_000.0,
    context: Optional[ScanContext] = None,
) -> Tuple[bool, float, str]:
    """
    Evaluates volume surge conditions.
    If context is provided, uses context-specific volume threshold (e.g. 1.3x for MID_DAY).
    Returns: (is_spike: bool, volume_multiplier: float, reason: str)
    """
    if context is not None and multiplier_threshold == 1.5:
        multiplier_threshold = context.volume_threshold

    if avg_volume_20d <= 0:
        return False, 0.0, "Historical average volume is zero or unavailable"

    multiplier = round(current_volume / avg_volume_20d, 2)

    if current_turnover < min_turnover:
        return (
            False,
            multiplier,
            f"Daily turnover (Rp{current_turnover:,.0f}) is below Rp{min_turnover:,.0f}",
        )

    if multiplier < multiplier_threshold:
        return (
            False,
            multiplier,
            f"Volume multiplier {multiplier}x is below required {multiplier_threshold}x threshold",
        )

    return True, multiplier, ""
