import pytest
from risk_engine.tick_size import (
    get_tick_size,
    round_to_tick,
    calculate_ara_limit,
    calculate_arb_limit,
    is_near_ara,
)


def test_tick_sizes():
    # < Rp200: Rp1
    assert get_tick_size(150) == 1
    assert get_tick_size(199) == 1

    # Rp200 - < Rp500: Rp2
    assert get_tick_size(200) == 2
    assert get_tick_size(498) == 2

    # Rp500 - < Rp2000: Rp5
    assert get_tick_size(500) == 5
    assert get_tick_size(1995) == 5

    # Rp2000 - < Rp5000: Rp10
    assert get_tick_size(2000) == 10
    assert get_tick_size(4990) == 10

    # >= Rp5000: Rp25
    assert get_tick_size(5000) == 25
    assert get_tick_size(8500) == 25


def test_round_to_tick():
    # Test rounding within 500-2000 range (tick 5)
    assert round_to_tick(1234, mode="nearest") == 1235
    assert round_to_tick(1234, mode="floor") == 1230
    assert round_to_tick(1234, mode="ceil") == 1235

    # Test rounding in >= 5000 range (tick 25)
    assert round_to_tick(5012, mode="nearest") == 5000
    assert round_to_tick(5013, mode="nearest") == 5025

    # Test bottom floor (50 IDR)
    assert round_to_tick(45) == 50


def test_ara_arb_limits():
    # Range 50 - 200 (± 35%)
    # Prev close = 100 -> ARA = 135
    assert calculate_ara_limit(100) == 135
    assert calculate_arb_limit(100) == 65

    # Range > 200 - 5000 (± 25%)
    # Prev close = 4000 -> ARA = 5000
    assert calculate_ara_limit(4000) == 5000

    # Range > 5000 (± 20%)
    # Prev close = 6000 -> ARA = 7200
    assert calculate_ara_limit(6000) == 7200


def test_is_near_ara():
    # Prev close = 5000 -> ARA = 6250. Tick at 6200 is 25.
    # Threshold 2 ticks below ARA = 6250 - 50 = 6200.
    blocked, reason = is_near_ara(6200, 5000, buffer_ticks=2)
    assert blocked is True

    # Safe price at 5800
    blocked_safe, _ = is_near_ara(5800, 5000, buffer_ticks=2)
    assert blocked_safe is False
