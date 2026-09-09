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
