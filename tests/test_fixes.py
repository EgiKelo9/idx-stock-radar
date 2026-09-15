import json
from datetime import datetime
from unittest.mock import MagicMock, patch
from analyzer.sentiment import LLMSentimentAnalyzer
from config import config
from fetcher.broker_flow import BrokerFlowFetcher
from fetcher.disclosure import DisclosureFetcher
from fetcher.ticker_list import TickerListFetcher
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
