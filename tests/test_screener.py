import numpy as np
import pandas as pd
from models.ticker import BrokerItem, Ticker
from screener.broker_analysis import analyze_broker_flow, classify_accumulation_ratio
from screener.eligibility import check_ticker_eligibility
from screener.technical import calculate_indicators, detect_technical_setup
from screener.volume_spike import check_volume_spike


def test_layer_0_eligibility():
    # Eligible stock
    t_valid = Ticker(symbol="BBCA", board="UTAMA", avg_turnover_20d=10_000_000_000.0)
    is_ok, _ = check_ticker_eligibility(t_valid)
    assert is_ok is True

    # Ineligible: FCA board
    t_fca = Ticker(symbol="GOTO", board="FCA", avg_turnover_20d=5_000_000_000.0)
    is_ok, reason = check_ticker_eligibility(t_fca)
    assert is_ok is False
    assert "FCA" in reason

    # Ineligible: Suspended
    t_susp = Ticker(symbol="BUMI", board="UTAMA", is_suspended=True, avg_turnover_20d=5_000_000_000.0)
    is_ok, reason = check_ticker_eligibility(t_susp)
    assert is_ok is False
    assert "suspended" in reason

    # Ineligible: Low turnover (< 1B)
    t_illiquid = Ticker(symbol="ZBRA", board="PENGEMBANGAN", avg_turnover_20d=400_000_000.0)
    is_ok, reason = check_ticker_eligibility(t_illiquid)
    assert is_ok is False
    assert "turnover" in reason


def test_layer_1_volume_spike():
    # Pass: 1.5x volume and >= 1B turnover
    passed, mult, _ = check_volume_spike(
        current_volume=150_000,
        avg_volume_20d=100_000,
        current_turnover=1_500_000_000.0,
    )
    assert passed is True
    assert mult == 1.5

    # Reject: Low turnover
    passed, _, reason = check_volume_spike(
        current_volume=300_000,
        avg_volume_20d=100_000,
        current_turnover=500_000_000.0,
    )
    assert passed is False
    assert "turnover" in reason

    # Reject: Volume below 1.5x
    passed, mult, reason = check_volume_spike(
        current_volume=120_000,
        avg_volume_20d=100_000,
        current_turnover=2_000_000_000.0,
    )
    assert passed is False
    assert mult == 1.2


def test_layer_2_technical_indicators():
    # Generate 60 days of synthetic trending price data
    np.random.seed(42)
    closes = np.linspace(4000, 4800, 60)
    highs = closes + 50
    lows = closes - 50
    opens = closes - 10
    vols = [1_000_000] * 60

    df = pd.DataFrame({
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": vols,
    })

    df_ind = calculate_indicators(df)
    assert "sma_20" in df_ind.columns
    assert "sma_50" in df_ind.columns
    assert "rsi" in df_ind.columns
    assert "atr" in df_ind.columns
    assert df_ind["rsi"].iloc[-1] > 0


def test_layer_3_bandarmologi_classification():
    # Test ratio classification buckets
    assert classify_accumulation_ratio(0.25) == "BIG_ACCUM"
    assert classify_accumulation_ratio(0.10) == "SMALL_ACCUM"
    assert classify_accumulation_ratio(0.01) == "NEUTRAL"
    assert classify_accumulation_ratio(-0.10) == "SMALL_DIST"
    assert classify_accumulation_ratio(-0.30) == "BIG_DIST"

    # Test complete summary calculation
    buyers = [
        BrokerItem(broker_code="ZP", volume=50_000, value=250_000_000.0),
        BrokerItem(broker_code="BK", volume=30_000, value=150_000_000.0),
        BrokerItem(broker_code="AK", volume=20_000, value=100_000_000.0),
    ]
    sellers = [
        BrokerItem(broker_code="YP", volume=10_000, value=50_000_000.0),
        BrokerItem(broker_code="PD", volume=5_000, value=25_000_000.0),
        BrokerItem(broker_code="XC", volume=5_000, value=25_000_000.0),
    ]
    summary = analyze_broker_flow(
        symbol="BBRI",
        date_str="20260909",
        total_volume=200_000,
        top_buyers=buyers,
        top_sellers=sellers,
        foreign_net_buy=6_000_000_000.0,
    )

    # Net buy top 3 = 100,000 - 20,000 = 80,000.
    # Ratio = 80,000 / 200,000 = 0.40 -> BIG_ACCUM
    assert summary.accum_rank == "BIG_ACCUM"
    assert summary.foreign_accum_rank == "HIGH_ACCUM"


def test_contextual_screener_rules():
    from models.scan_context import ScanContext

    # Test 1: MID_DAY volume threshold allows 1.3x
    passed, mult, _ = check_volume_spike(
        current_volume=135_000,
        avg_volume_20d=100_000,
        current_turnover=2_000_000_000.0,
        context=ScanContext.MID_DAY,
    )
    assert passed is True
    assert mult == 1.35

    # PRE_MARKET requires >= 1.5x, so 1.35x fails
    passed_pre, _, reason_pre = check_volume_spike(
        current_volume=135_000,
        avg_volume_20d=100_000,
        current_turnover=2_000_000_000.0,
        context=ScanContext.PRE_MARKET,
    )
    assert passed_pre is False
    assert "1.5x" in reason_pre

    # Test 2: END_MARKET detects CONTRACTION_SETUP (inside bar, drying volume <= 0.7x, above SMA20)
    prices = [1000.0 + i * 2 + (5 if i % 2 == 0 else -5) for i in range(60)]
    closes = prices[:-2] + [1120.0, 1118.0]
    opens = [p - 1 for p in closes]
    highs = [p + 8 for p in closes]
    highs[-1] = 1122.0  # inside bar: high <= prev high (1128)
    lows = [p - 8 for p in closes]
    lows[-1] = 1114.0   # inside bar: low >= prev low (1112)
    vols = [100_000] * 59 + [50_000]  # drying volume 0.5x

    df = pd.DataFrame({"open": opens, "high": highs, "low": lows, "close": closes, "volume": vols})
    df_ind = calculate_indicators(df)

    setup_end, _ = detect_technical_setup(df_ind, volume_multiplier=0.5, context=ScanContext.END_MARKET)
    assert setup_end == "CONTRACTION_SETUP"

    # PRE_MARKET should not permit CONTRACTION_SETUP
    setup_pre, _ = detect_technical_setup(df_ind, volume_multiplier=0.5, context=ScanContext.PRE_MARKET)
    assert setup_pre is None
