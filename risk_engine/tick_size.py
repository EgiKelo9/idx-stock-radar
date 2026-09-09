from math import floor, ceil
from typing import Tuple


def get_tick_size(price: float) -> int:
    """
    Returns official IDX tick size for a given price according to §4.2.
    < Rp200: Rp1
    Rp200 - < Rp500: Rp2
    Rp500 - < Rp2000: Rp5
    Rp2000 - < Rp5000: Rp10
    >= Rp5000: Rp25
    """
    if price < 200:
        return 1
    elif price < 500:
        return 2
    elif price < 2000:
        return 5
    elif price < 5000:
        return 10
    else:
        return 25


def round_to_tick(price: float, mode: str = "nearest") -> int:
    """
    Rounds a floating price to the nearest valid official IDX price tick.
    mode: 'nearest', 'floor' (for Stop Loss safety), 'ceil' (for Targets)
    """
    if price <= 50:
        return 50  # Regular board bottom floor in IDR

    tick = get_tick_size(price)
    if mode == "floor":
        rounded = floor(price / tick) * tick
    elif mode == "ceil":
        rounded = ceil(price / tick) * tick
    else:
        rounded = round(price / tick) * tick

    # Re-check boundary tick transition (e.g. crossing from 199 to 200)
    adjusted_tick = get_tick_size(rounded)
    if rounded % adjusted_tick != 0:
        if mode == "floor":
            rounded = floor(rounded / adjusted_tick) * adjusted_tick
        elif mode == "ceil":
            rounded = ceil(rounded / adjusted_tick) * adjusted_tick
        else:
            rounded = round(rounded / adjusted_tick) * adjusted_tick

    return max(50, int(rounded))


def get_auto_rejection_rate(price: float) -> float:
    """
    Returns symmetric ARA/ARB percentage:
    Rp50 - Rp200: 35% (0.35)
    > Rp200 - Rp5,000: 25% (0.25)
    > Rp5,000: 20% (0.20)
    """
    if price <= 200:
        return 0.35
    elif price <= 5000:
        return 0.25
    else:
        return 0.20


def calculate_ara_limit(previous_close: float) -> int:
    """
    Calculates Auto Rejection Atas (ARA) limit rounded to nearest valid tick.
    """
    rate = get_auto_rejection_rate(previous_close)
    raw_ara = previous_close * (1.0 + rate)
    return round_to_tick(raw_ara, mode="floor")


def calculate_arb_limit(previous_close: float) -> int:
    """
    Calculates Auto Rejection Bawah (ARB) limit rounded to nearest valid tick.
    """
    rate = get_auto_rejection_rate(previous_close)
    raw_arb = previous_close * (1.0 - rate)
    return round_to_tick(raw_arb, mode="ceil")


def is_near_ara(
    current_price: float,
    previous_close: float,
    buffer_ticks: int = 2,
    buffer_percent: float = 1.5,
) -> Tuple[bool, str]:
    """
    Checks if current price is too close to ARA limit:
    1. current_price >= (ara_limit - (buffer_ticks * tick_size))
    2. distance to ARA <= buffer_percent (e.g. 1.5%)
    Returns: (is_blocked: bool, reason: str)
    """
    ara_limit = calculate_ara_limit(previous_close)
    tick = get_tick_size(current_price)

    # Tick-based rule (§4.1)
    threshold_price = ara_limit - (buffer_ticks * tick)
    if current_price >= threshold_price:
        return True, f"Price {current_price} is within {buffer_ticks} ticks of ARA ({ara_limit})"

    # Percentage-based rule (FR-05: <= 1.5% from ARA)
    pct_from_ara = ((ara_limit - current_price) / ara_limit) * 100.0
    if pct_from_ara <= buffer_percent:
        return True, f"Price {current_price} is {pct_from_ara:.2f}% from ARA ({ara_limit}), exceeding {buffer_percent}% safety buffer"

    return False, ""
