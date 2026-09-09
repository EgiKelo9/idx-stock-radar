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
