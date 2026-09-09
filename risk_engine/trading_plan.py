from typing import Optional, Tuple
from models.signal import TradingParameters
from risk_engine.tick_size import round_to_tick


def generate_trading_plan(
    current_price: float,
    atr: float,
    atr_multiplier: float = 1.5,
    min_rrr: float = 2.0,
    tp2_multiplier: float = 3.0,
) -> Tuple[Optional[TradingParameters], str]:
    """
    Constructs a verified trading plan for a buy signal.
    Returns: (TradingParameters or None, reason if rejected)
    """
    if current_price <= 50:
        return None, "Current price at or below 50 IDR floor"

    if atr <= 0:
        return None, "Invalid or non-positive ATR value"

    entry = round_to_tick(current_price, mode="nearest")

    # Stop Loss calculated with ATR tolerance (FR-05 & US-02: max 1.5 * ATR)
    raw_risk = atr_multiplier * atr
    raw_sl = entry - raw_risk
    sl = round_to_tick(raw_sl, mode="floor")

    # Risk must be strictly positive and viable
    risk = entry - sl
    if risk <= 0:
        return None, f"Stop Loss ({sl}) must be strictly below Entry ({entry})"

    # Take Profit 1 target with minimum required RRR (at least 1:2)
    raw_tp1 = entry + (min_rrr * risk)
    tp1 = round_to_tick(raw_tp1, mode="ceil")

    # Take Profit 2 target (default 1:3 RRR)
    raw_tp2 = entry + (tp2_multiplier * risk)
    tp2 = round_to_tick(raw_tp2, mode="ceil")

    # Recalculate actual realized RRR after tick size rounding
    actual_rrr = round((tp1 - entry) / risk, 2)

    if actual_rrr < min_rrr:
        # Step up TP1 to next ticks to guarantee minimum RRR >= min_rrr
        while (tp1 - entry) / risk < min_rrr:
            from risk_engine.tick_size import get_tick_size
            tp1 += get_tick_size(tp1)
        actual_rrr = round((tp1 - entry) / risk, 2)

    plan = TradingParameters(
        entry=float(entry),
        stop_loss=float(sl),
        take_profit_1=float(tp1),
        take_profit_2=float(tp2),
        rrr=float(actual_rrr),
    )
    return plan, ""
