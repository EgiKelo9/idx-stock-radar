from typing import Tuple
from config import config


def check_volume_spike(
    current_volume: int,
    avg_volume_20d: float,
    current_turnover: float,
    multiplier_threshold: float = 1.5,
    min_turnover: float = 1_000_000_000.0,
) -> Tuple[bool, float, str]:
    """
    Evaluates volume surge conditions.
    Returns: (is_spike: bool, volume_multiplier: float, reason: str)
    """
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
