from models.signal import SignalMetrics, SignalPayload, TradingParameters
from notifier.formatter import format_signal_message, escape_markdown, OFFICIAL_OJK_DISCLAIMER


def test_telegram_message_formatting():
    sig = SignalPayload(
        ticker="BBRI",
        company_name="Bank Rakyat Indonesia",
        setup_type="PULLBACK_REBOUND",
        parameters=TradingParameters(
            entry=4950.0,
            stop_loss=4800.0,
            take_profit_1=5250.0,
            take_profit_2=5450.0,
            rrr=2.0,
        ),
        metrics=SignalMetrics(
            rsi=41.2,
            volume_multiplier=2.3,
            foreign_accum_rank="HIGH",
            broker_accum_rank="BIG_ACCUM",
        ),
        ai_context="Kinerja pertumbuhan kredit mikro stabil di atas rata-rata industri.",
    )

    msg = format_signal_message(sig)

    # Verify header & ticker info
    assert "IDX STOCK RADAR - NEW SIGNAL" in msg
    assert "BBRI (Bank Rakyat Indonesia)" in msg
    assert "PULLBACK\\_REBOUND" in msg

    # Verify trading plan
    assert "Rp4,950" in msg
    assert "Rp4,800" in msg
    assert "Rp5,250" in msg
    assert "1:2.0" in msg

    # Verify metrics
    assert "41.2" in msg
    assert "2.3x" in msg
    assert "BIG\\_ACCUM" in msg

    # Verify AI context
    assert "Kinerja pertumbuhan kredit mikro stabil" in msg

    # Verify Official OJK Disclaimer
    assert "DISCLAIMER ON" in msg
    assert OFFICIAL_OJK_DISCLAIMER in msg


def test_escape_markdown_special_characters():
    raw = "Test_with_underscores *bold* `code` and [brackets]"
    escaped = escape_markdown(raw)
    assert "\\_" in escaped
    assert "\\*" in escaped
    assert "\\`" in escaped
    assert "\\[" in escaped
    assert escaped == "Test\\_with\\_underscores \\*bold\\* \\`code\\` and \\[brackets]"


def test_format_signal_with_problematic_chars():
    sig = SignalPayload(
        ticker="AKSI",
        company_name="PT Maja_Agung*Test",
        setup_type="PULLBACK_REBOUND",
        parameters=TradingParameters(
            entry=100.0,
            stop_loss=90.0,
            take_profit_1=120.0,
            take_profit_2=130.0,
            rrr=2.0,
        ),
        metrics=SignalMetrics(
            rsi=30.0,
            volume_multiplier=1.8,
            foreign_accum_rank="NEUTRAL",
            broker_accum_rank="NEUTRAL",
        ),
        ai_context='Pengumuman: [Tag: Corporate Action] with "sentiment_score": 0.85 & *risk*',
    )

    msg = format_signal_message(sig)
    # Check that problematic underscores and brackets in ai_context are escaped
    assert "\\[Tag:" in msg
    assert "sentiment\\_score" in msg
    assert "\\*risk\\*" in msg
    # Verify closing disclaimer is present
    assert OFFICIAL_OJK_DISCLAIMER in msg
