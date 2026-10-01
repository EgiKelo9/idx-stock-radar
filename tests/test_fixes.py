import json
from datetime import datetime
from unittest.mock import MagicMock, patch
from analyzer.sentiment import LLMSentimentAnalyzer
from config import config
from fetcher.broker_flow import BrokerFlowFetcher
from fetcher.disclosure import DisclosureFetcher
from fetcher.ticker_list import TickerListFetcher
from models.sentiment import SentimentResult
from models.ticker import BrokerItem, BrokerSummary
from utils.market_calendar import MarketCalendar


def test_broker_flow_idx_flat_list_parsing():
    """Validates that broker_flow.py parses official IDX GetBrokerSummary structure (flat list with IDFirm)."""
    fetcher = BrokerFlowFetcher()
    sample_response = {
        "draw": 0,
        "recordsTotal": 3,
        "recordsFiltered": 3,
        "data": [
            {
                "No": 1,
                "IDFirm": "AK",
                "FirmName": "UBS Sekuritas Indonesia",
                "Volume": 3_964_925_064,
                "Value": 3_370_306_742_036.0,
                "Frequency": 250196,
            },
            {
                "No": 2,
                "IDFirm": "YP",
                "FirmName": "Mirae Asset Sekuritas",
                "Volume": 300_000_000,
                "Value": 100_000_000_000.0,
                "Frequency": 10000,
            },
            {
                "No": 3,
                "IDFirm": "PD",
                "FirmName": "Indo Premier Sekuritas",
                "Volume": 200_000_000,
                "Value": 50_000_000_000.0,
                "Frequency": 5000,
            },
        ],
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = sample_response

    with patch.object(fetcher.session, "get", return_value=mock_resp):
        summary = fetcher.fetch_broker_summary("BBCA", "20260909")

    assert summary.symbol == "BBCA"
    assert summary.total_volume == 3_964_925_064 + 300_000_000 + 200_000_000
    assert len(summary.top3_buyers) > 0
    assert summary.top3_buyers[0].broker_code == "AK"
    assert summary.foreign_accum_rank == "HIGH_ACCUM"


def test_disclosure_get_news_search_parsing():
    """Validates disclosure fetcher parsing from GetNewsSearch response format."""
    fetcher = DisclosureFetcher(max_words=20)
    sample_news = {
        "Items": [
            {
                "Id": 11809,
                "Title": "Laba Bersih Kuartal III Melonjak",
                "Summary": "Perseroan mencatatkan kenaikan laba bersih secara signifikan didorong pertumbuhan pendapatan operasional.",
                "Tags": "Laporan Keuangan,BBCA",
            }
        ],
        "ItemCount": 1,
    }

    with patch.object(fetcher, "_fetch_url", return_value=sample_news):
        text = fetcher.fetch_latest_disclosure("BBCA")

    assert text is not None
    assert "Laba Bersih Kuartal III Melonjak" in text
    assert "Detail:" in text
    assert len(text.split()) <= 25


def test_openrouter_sentiment_analyzer():
    """Validates OpenRouter LLM sentiment analysis and markdown fence stripping."""
    analyzer = LLMSentimentAnalyzer()
    analyzer.openrouter_key = "test_key"

    sample_md = """```json
    {
      "ticker": "BBCA",
      "sentiment_score": 0.75,
      "sentiment_label": "POSITIVE",
      "catalyst_event": "FINANCIAL_REPORT",
      "summary": "Kinerja kuartal positif.",
      "risk_flags": []
    }
    ```"""

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": sample_md}}]
    }

    with patch("httpx.Client.post", return_value=mock_resp):
        res = analyzer._call_openrouter("BBCA", "Teks laporan keuangan")

    assert res is not None
    assert res.ticker == "BBCA"
    assert res.sentiment_score == 0.75
    assert res.sentiment_label == "POSITIVE"
    assert res.catalyst_event == "FINANCIAL_REPORT"


def test_ticker_list_universe_and_boards():
    """Validates universe parsing with 962 emiten and board normalization."""
    fetcher = TickerListFetcher()

    sample_universe = {
        "recordsTotal": 4,
        "data": [
            {"KodeEmiten": "BBCA", "NamaEmiten": "Bank Central Asia", "PapanPencatatan": "Utama", "EfekEmiten_Saham": True, "Status": 0},
            {"KodeEmiten": "GOTO", "NamaEmiten": "GoTo Gojek Tokopedia", "PapanPencatatan": "Ekonomi Baru", "EfekEmiten_Saham": True, "Status": 0},
            {"KodeEmiten": "FCA1", "NamaEmiten": "Saham Khusus", "PapanPencatatan": "Pemantauan Khusus", "EfekEmiten_Saham": True, "Status": 0},
            {"KodeEmiten": "OBL1", "NamaEmiten": "Obligasi A", "PapanPencatatan": "Utama", "EfekEmiten_Saham": False, "Status": 0},
        ],
    }

    # Filter with UTAMA
    parsed = fetcher._parse_ticker_data(sample_universe, allowed_boards={"UTAMA"})
    symbols = [t.symbol for t in parsed]
    assert "BBCA" in symbols
    assert "GOTO" in symbols  # Ekonomi Baru mapped to UTAMA
    assert "FCA1" not in symbols
    assert "OBL1" not in symbols  # Excluded non-stock

    # Filter with ALL
    parsed_all = fetcher._parse_ticker_data(sample_universe, allowed_boards={"ALL"})
    symbols_all = [t.symbol for t in parsed_all]
    assert "BBCA" in symbols_all
    assert "FCA1" in symbols_all
    assert "OBL1" not in symbols_all


def test_dynamic_market_calendar_multiyear():
    """Validates dynamic holiday detection across multiple future and past years."""
    cal = MarketCalendar()

    # Dynamic years
    assert cal.is_holiday(datetime(2025, 1, 1)) is True
    assert cal.is_holiday(datetime(2026, 1, 1)) is True
    assert cal.is_holiday(datetime(2027, 1, 1)) is True
    assert cal.is_holiday(datetime(2030, 1, 1)) is True

    # Normal trading day
    assert cal.is_holiday(datetime(2026, 9, 9)) is False

    # Weekend check
    assert cal.is_weekend(datetime(2026, 9, 12)) is True  # Saturday
    assert cal.is_weekend(datetime(2026, 9, 9)) is False   # Wednesday


def test_ticker_list_curl_fallback_cross_platform():
    """Validates that TickerListFetcher dynamically resolves curl binary on Linux/Windows and falls back properly."""
    fetcher = TickerListFetcher()

    # Case 1: requests gets 403, curl is resolved via shutil.which
    mock_resp = MagicMock()
    mock_resp.status_code = 403

    mock_curl_proc = MagicMock()
    mock_curl_proc.returncode = 0
    mock_curl_proc.stdout = json.dumps({
        "data": [
            {"KodeEmiten": "BBCA", "NamaEmiten": "Bank Central Asia", "PapanPencatatan": "Utama", "EfekEmiten_Saham": True, "Status": 0}
        ]
    })

    with patch.object(fetcher.session, "get", return_value=mock_resp), \
        patch("shutil.which", return_value="/usr/bin/curl"), \
        patch("subprocess.run", return_value=mock_curl_proc) as mock_subproc:

        result = fetcher._fetch_from_network()
        assert result is not None
        assert "data" in result
        assert result["data"][0]["KodeEmiten"] == "BBCA"

        # Ensure curl was invoked with /usr/bin/curl, NOT hardcoded curl.exe
        called_cmd = mock_subproc.call_args[0][0]
        assert called_cmd[0] == "/usr/bin/curl"
        assert "-H" in called_cmd
        assert any("Referer:" in arg for arg in called_cmd)


def test_broker_flow_smart_date_and_data_na_fallback():
    """Validates that off-hours queries without date resolve to D-1 and return DATA_N/A when empty."""
    fetcher = BrokerFlowFetcher()
    cal = fetcher.calendar

    # Mock time at 08:30 WIB on a Tuesday (2026-09-15 08:30 WIB)
    tz_wib = cal.tz
    morning_dt = datetime(2026, 9, 15, 8, 30, tzinfo=tz_wib)

    with patch.object(cal, "get_current_time", return_value=morning_dt):
        effective_date = fetcher._determine_effective_date()
        # Monday 2026-09-14 should be the settled D-1 date
        assert effective_date == "20260914"

    # Mock empty response from IDX -> should return DATA_N/A instead of NEUTRAL
    mock_resp = MagicMock()
    mock_resp.status_code = 404

    with patch.object(fetcher.session, "get", return_value=mock_resp):
        summary = fetcher.fetch_broker_summary("AKRA", reference_date="20260914")
        assert summary.accum_rank == "DATA_N/A"
        assert summary.foreign_accum_rank == "DATA_N/A"
        assert summary.total_volume == 0

        # In-memory cache test: second call should not call session.get again
        fetcher.session.get.reset_mock()
        cached_summary = fetcher.fetch_broker_summary("AKRA", reference_date="20260914")
        assert cached_summary.accum_rank == "DATA_N/A"
        fetcher.session.get.assert_not_called()


def test_ticker_list_curl_cffi_tier_success():
    """Validates that _fetch_cffi succeeds and bypasses standard requests session."""
    fetcher = TickerListFetcher()

    mock_cffi_resp = MagicMock()
    mock_cffi_resp.status_code = 200
    mock_cffi_resp.json.return_value = {
        "data": [
            {"KodeEmiten": "BBCA", "NamaEmiten": "Bank Central Asia", "PapanPencatatan": "Utama", "EfekEmiten_Saham": True, "Status": 0},
            {"KodeEmiten": "RUNS", "NamaEmiten": "Global Sukses Solusi", "PapanPencatatan": "Akselerasi", "EfekEmiten_Saham": True, "Status": 0},
        ]
    }

    with patch.object(fetcher, "_fetch_cffi", return_value=mock_cffi_resp.json.return_value):
        data = fetcher._fetch_from_network()
        assert data is not None
        assert len(data["data"]) == 2
        assert data["data"][1]["KodeEmiten"] == "RUNS"


def test_ticker_list_akselerasi_included_in_default():
    """Validates that AKSELERASI board is accepted under new default configuration."""
    fetcher = TickerListFetcher()

    sample_universe = {
        "data": [
            {"KodeEmiten": "BBCA", "NamaEmiten": "Bank Central Asia", "PapanPencatatan": "Utama", "EfekEmiten_Saham": True, "Status": 0},
            {"KodeEmiten": "BRIS", "NamaEmiten": "Bank Syariah Indonesia", "PapanPencatatan": "Pengembangan", "EfekEmiten_Saham": True, "Status": 0},
            {"KodeEmiten": "RUNS", "NamaEmiten": "Global Sukses Solusi", "PapanPencatatan": "Akselerasi", "EfekEmiten_Saham": True, "Status": 0},
            {"KodeEmiten": "FCA1", "NamaEmiten": "Saham Khusus", "PapanPencatatan": "Pemantauan Khusus", "EfekEmiten_Saham": True, "Status": 0},
        ]
    }

    allowed = {b.strip().upper() for b in config.system.ticker_boards.split(",")}
    assert "AKSELERASI" in allowed
    parsed = fetcher._parse_ticker_data(sample_universe, allowed_boards=allowed)
    symbols = [t.symbol for t in parsed]
    assert "BBCA" in symbols
    assert "BRIS" in symbols
    assert "RUNS" in symbols
    assert "FCA1" not in symbols


def test_broker_flow_bulk_cache_stores_empty():
    """Validates that empty bulk stock summary response is cached to prevent WAF flood."""
    fetcher = BrokerFlowFetcher()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": []}

    with patch.object(fetcher.session, "get", return_value=mock_resp):
        res1 = fetcher.get_stock_summary_bulk("20260930")
        assert res1 == {}
        assert "20260930" in fetcher._stock_summary_cache
        assert fetcher._stock_summary_cache["20260930"] == {}

        # Second call must hit in-memory cache and not make any HTTP requests
        fetcher.session.get.reset_mock()
        res2 = fetcher.get_stock_summary_bulk("20260930")
        assert res2 == {}
        fetcher.session.get.assert_not_called()


def test_broker_flow_fallback_to_previous_trading_day():
    """Validates that when primary date returns None, fetch_broker_summary falls back to D-1 and succeeds."""
    fetcher = BrokerFlowFetcher()

    # When querying 20260915, primary fails (None), but D-1 (20260914) succeeds
    def mock_query(clean_symbol, date_str):
        if date_str == "20260915":
            return None
        elif date_str == "20260914":
            return BrokerSummary(
                symbol=clean_symbol,
                date=date_str,
                total_volume=1_000_000,
                top3_buyers=[],
                top3_sellers=[],
                top3_net_buy_volume=200_000,
                top3_accumulation_ratio=0.20,
                accum_rank="BIG_ACCUM",
                foreign_accum_rank="ACCUM",
            )
        return None

    with patch.object(fetcher, "_query_idx_endpoint", side_effect=mock_query):
        summary = fetcher.fetch_broker_summary("BBCA", target_date="20260915")
        assert summary is not None
        assert summary.symbol == "BBCA"
        assert summary.date == "20260914"
        assert summary.accum_rank == "BIG_ACCUM"
        assert summary.foreign_accum_rank == "ACCUM"


def test_sentiment_analyzer_prefilter_materiality():
    """Validates that routine non-material disclosures are filtered out without LLM invocation."""
    analyzer = LLMSentimentAnalyzer()

    # Routine non-material text
    routine_text = "Laporan Bulanan Registrasi Pemegang Efek Periode September 2026 PT Bank Central Asia Tbk"
    is_mat, reason = analyzer.is_material_disclosure(routine_text)
    assert is_mat is False
    assert "rutin" in reason.lower()

    # Analyze routine text directly -> returns neutral fallback without calling LLM
    with patch.object(analyzer, "_execute_with_fallback") as mock_exec:
        res = analyzer.analyze("BBCA", routine_text)
        assert res.sentiment_label == "NEUTRAL"
        assert res.sentiment_score == 0.0
        mock_exec.assert_not_called()

    # Highly material text
    material_text = "Perseroan mengumumkan pembagian dividen interim tunai sebesar Rp 150 per saham dan kenaikan laba bersih 25%."
    is_mat_2, _ = analyzer.is_material_disclosure(material_text)
    assert is_mat_2 is True


def test_sentiment_analyzer_multi_provider_fallback_on_429():
    """Validates that a 429 quota exhaustion on Gemini immediately cascades to OpenRouter."""
    analyzer = LLMSentimentAnalyzer()
    analyzer.provider = "gemini"
    analyzer.gemini_key = "fake_gemini_key"
    analyzer.openrouter_key = "fake_openrouter_key"

    material_text = "Perseroan mencatatkan lonjakan laba bersih kuartal III sebesar 40%."

    # Gemini raises quota error 429
    def mock_gemini(ticker, text):
        raise Exception("429 You exceeded your current quota: generativelanguage.googleapis.com")

    # OpenRouter succeeds
    expected_result = SentimentResult(
        ticker="BBCA",
        sentiment_score=0.8,
        sentiment_label="POSITIVE",
        catalyst_event="FINANCIAL_REPORT",
        summary="Lonjakan laba bersih 40%.",
        risk_flags=[],
    )

    with patch.object(analyzer, "_call_gemini", side_effect=mock_gemini), \
         patch.object(analyzer, "_call_openrouter", return_value=expected_result) as mock_openrouter, \
         patch.object(analyzer, "_pace_call"):

        res = analyzer.analyze("BBCA", material_text)
        assert res.sentiment_label == "POSITIVE"
        assert res.sentiment_score == 0.8
        mock_openrouter.assert_called_once()
        # Ensure Gemini is now placed in cooldown
        assert analyzer._is_provider_in_cooldown("gemini") is True


def test_sentiment_analyzer_cooldown_skips_provider():
    """Validates that a provider in active cooldown is immediately skipped on subsequent requests."""
    analyzer = LLMSentimentAnalyzer()
    analyzer.provider = "gemini"
    analyzer.gemini_key = "fake_gemini_key"
    analyzer.openrouter_key = "fake_openrouter_key"

    # Set Gemini in cooldown
    analyzer._set_provider_cooldown("gemini", duration_seconds=600.0)
    assert analyzer._is_provider_in_cooldown("gemini") is True

    material_text = "Perseroan mengumumkan akuisisi 100% saham entitas manufaktur."
    expected_result = SentimentResult(
        ticker="ASII",
        sentiment_score=0.6,
        sentiment_label="POSITIVE",
        catalyst_event="CORPORATE_ACTION",
        summary="Akuisisi entitas manufaktur.",
        risk_flags=[],
    )

    with patch.object(analyzer, "_call_gemini") as mock_gemini, \
         patch.object(analyzer, "_call_openrouter", return_value=expected_result) as mock_openrouter, \
         patch.object(analyzer, "_pace_call"):

        res = analyzer.analyze("ASII", material_text)
        assert res.ticker == "ASII"
        mock_gemini.assert_not_called()
        mock_openrouter.assert_called_once()


def test_market_regime_detection_mocked():
    """Validates IHSG trend classification into BULLISH, BEARISH, and SIDEWAYS."""
    import pandas as pd
    from screener.market_regime import MarketRegimeDetector

    detector = MarketRegimeDetector()

    # Generate synthetic price series for Bullish scenario
    dates = pd.date_range("2026-06-01", periods=60, freq="B")
    bullish_prices = [5000 + i * 20 for i in range(60)]  # Uptrend
    df_bullish = pd.DataFrame({"Close": bullish_prices}, index=dates)

    with patch("yfinance.Ticker.history", return_value=df_bullish):
        res = detector.detect_regime(force_refresh=True)
        assert res.regime == "BULLISH"
        assert res.ihsg_price == bullish_prices[-1]
        assert "Uptrend" in res.description

    # Generate synthetic price series for Bearish scenario
    bearish_prices = [7000 - i * 30 for i in range(60)]  # Downtrend
    df_bearish = pd.DataFrame({"Close": bearish_prices}, index=dates)

    with patch("yfinance.Ticker.history", return_value=df_bearish):
        res_bear = detector.detect_regime(force_refresh=True)
        assert res_bear.regime == "BEARISH"
        assert "Downtrend" in res_bear.description


def test_data_quality_gate():
    """Validates that Data Quality Gate rejects malformed, incomplete, or corrupted candle data."""
    import pandas as pd
    from screener.data_quality import validate_candle_data

    # Case 1: Insufficient bars (< 20)
    df_short = pd.DataFrame({"open": [100]*10, "high": [105]*10, "low": [95]*10, "close": [102]*10, "volume": [1000]*10})
    ok, reason = validate_candle_data(df_short, min_bars=20)
    assert ok is False
    assert "tidak mencukupi" in reason.lower()

    # Case 2: Missing required column
    df_missing = pd.DataFrame({"open": [100]*25, "close": [102]*25, "volume": [1000]*25})
    ok_miss, reason_miss = validate_candle_data(df_missing)
    assert ok_miss is False
    assert "tidak ditemukan" in reason_miss.lower()

    # Case 3: Price anomaly (High < Low)
    df_bad = pd.DataFrame({"open": [100]*25, "high": [90]*25, "low": [110]*25, "close": [100]*25, "volume": [1000]*25})
    ok_bad, _ = validate_candle_data(df_bad)
    assert ok_bad is False

    # Case 4: Valid DataFrame
    df_valid = pd.DataFrame({"open": [100]*25, "high": [105]*25, "low": [95]*25, "close": [102]*25, "volume": [1000]*25})
    ok_valid, msg = validate_candle_data(df_valid)
    assert ok_valid is True
    assert "valid" in msg.lower()


def test_confidence_scorer_calculation():
    """Validates composite confidence score 0-100 and market regime weighting."""
    from models.signal import TradingParameters
    from screener.confidence_scorer import calculate_confidence_score

    broker_accum = BrokerSummary(
        symbol="BBRI",
        date="20260930",
        total_volume=50_000_000,
        top3_buyers=[],
        top3_sellers=[],
        top3_net_buy_volume=10_000_000,
        top3_accumulation_ratio=0.20,
        accum_rank="BIG_ACCUM",
        foreign_accum_rank="HIGH_ACCUM",
    )

    sentiment_pos = SentimentResult(
        ticker="BBRI",
        sentiment_score=0.8,
        sentiment_label="POSITIVE",
        catalyst_event="DIVIDEND_ANNOUNCEMENT",
        summary="Dividen interim jumbo.",
        risk_flags=[],
    )

    plan = TradingParameters(
        entry=5000.0,
        stop_loss=4800.0,
        take_profit_1=5600.0,
        take_profit_2=6000.0,
        rrr=3.0,
    )

    score_bullish = calculate_confidence_score(
        setup_type="BREAKOUT",
        volume_multiplier=2.8,
        rsi=55.0,
        broker_summary=broker_accum,
        sentiment=sentiment_pos,
        trading_plan=plan,
        market_regime="BULLISH",
    )
    # Strong setup with tailwind should score >= 80
    assert 80.0 <= score_bullish <= 100.0

    score_bearish = calculate_confidence_score(
        setup_type="BREAKOUT",
        volume_multiplier=2.8,
        rsi=55.0,
        broker_summary=broker_accum,
        sentiment=sentiment_pos,
        trading_plan=plan,
        market_regime="BEARISH",
    )
    # Bearish penalty should make bearish score lower than bullish
    assert score_bearish < score_bullish


def test_pipeline_global_ranking_and_top_n():
    """Validates that rank_and_dispatch selects Top-N by confidence score and deduplicates."""
    from models.signal import TradingParameters, SignalMetrics, SignalPayload
    from pipeline import SignalPipeline

    pipeline = SignalPipeline()
    # Mock notifier to not call real network
    pipeline.notifier.dispatch_signal = MagicMock(return_value=True)
    pipeline.db.log_signal = MagicMock(return_value=True)

    plan = TradingParameters(entry=1000, stop_loss=950, take_profit_1=1150, take_profit_2=1250, rrr=3.0)
    metrics = SignalMetrics(rsi=50, volume_multiplier=2.0, foreign_accum_rank="NEUTRAL", broker_accum_rank="NEUTRAL")

    # Create 8 candidate signals with different confidence scores
    candidates = []
    for i in range(8):
        c = SignalPayload(
            ticker=f"TICK{i}",
            company_name=f"Company {i}",
            setup_type="BREAKOUT",
            parameters=plan,
            metrics=metrics,
            ai_context="Context",
            confidence_score=float(50 + i * 5),  # TICK7 has 85, TICK6 has 80, ...
            scan_context="MID_DAY",
            scan_date="20260930",
        )
        candidates.append(c)

    # Add 1 duplicate of TICK7
    dup_tick7 = SignalPayload(
        ticker="TICK7",
        company_name="Company 7",
        setup_type="BREAKOUT",
        parameters=plan,
        metrics=metrics,
        ai_context="Context",
        confidence_score=85.0,
        scan_context="MID_DAY",
        scan_date="20260930",
    )
    candidates.append(dup_tick7)

    # Rank and dispatch with top_n = 3
    dispatched = pipeline.rank_and_dispatch(candidates=candidates, top_n=3)

    assert len(dispatched) == 3
    # Top candidate must be TICK7 (score 85)
    assert dispatched[0].ticker == "TICK7"
    assert dispatched[0].confidence_score == 85.0
    # Second candidate must be TICK6 (score 80)
    assert dispatched[1].ticker == "TICK6"
    assert dispatched[1].confidence_score == 80.0
    # Third candidate must be TICK5 (score 75)
    assert dispatched[2].ticker == "TICK5"
    assert dispatched[2].confidence_score == 75.0
    # Deduplication check: TICK7 was not dispatched twice
    tickers_sent = [s.ticker for s in dispatched]
    assert tickers_sent.count("TICK7") == 1




