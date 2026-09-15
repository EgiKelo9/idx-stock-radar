from risk_engine.trading_plan import generate_trading_plan


def test_trading_plan_basic_generation():
    # Example matching BBRI entry
    entry_price = 4950.0
    atr = 100.0  # SL = 4950 - 150 = 4800 (tick 10 -> valid)

    plan, err = generate_trading_plan(entry_price, atr=atr, min_rrr=2.0)
    assert err == ""
    assert plan is not None
    assert plan.entry == 4950.0
    assert plan.stop_loss == 4800.0
    assert plan.take_profit_1 >= 5250.0
    assert plan.rrr >= 2.0


def test_trading_plan_tick_alignment():
    # Check that all generated levels adhere to valid tick sizes
    entry_price = 1453.0  # In 500-2000 range, tick is 5
    atr = 30.0

    plan, err = generate_trading_plan(entry_price, atr=atr)
    assert plan is not None
    assert plan.entry % 5 == 0
    assert plan.stop_loss % 5 == 0
    assert plan.take_profit_1 % 5 == 0
    assert plan.take_profit_2 % 5 == 0


def test_trading_plan_rejection_cases():
    # Reject non-positive ATR
    plan, err = generate_trading_plan(1000.0, atr=0.0)
    assert plan is None
    assert "ATR" in err

    # Reject penny stock below 50 floor
    plan, err = generate_trading_plan(45.0, atr=5.0)
    assert plan is None
    assert "floor" in err


def test_trading_plan_with_resistance_targeting():
    # BBRI entry 4950, ATR 100, SL 4800, Risk = 150
    entry_price = 4950.0
    atr = 100.0

    # Case A: Resistance is high (5350, RRR = 400 / 150 = 2.67 >= 2.0)
    plan_res, err = generate_trading_plan(entry_price, atr=atr, resistance_20d=5350.0)
    assert err == ""
    assert plan_res is not None
    assert plan_res.take_profit_1 == 5350.0
    assert plan_res.rrr >= 2.6
    assert plan_res.take_profit_2 > plan_res.take_profit_1

    # Case B: Resistance is too low/close (5100, RRR = 1.0 < 2.0) -> Fallback to min_rrr (>= 5250)
    plan_fallback, err = generate_trading_plan(entry_price, atr=atr, resistance_20d=5100.0)
    assert err == ""
    assert plan_fallback is not None
    assert plan_fallback.take_profit_1 >= 5250.0
    assert plan_fallback.rrr >= 2.0

    # Case C: TP2 default multiplier is 3.5 (4950 + 3.5 * 150 = 5475 -> tick 25 -> 5475)
    plan_tp2, _ = generate_trading_plan(entry_price, atr=atr, resistance_20d=None)
    assert plan_tp2 is not None
    assert plan_tp2.take_profit_2 == 5475.0
