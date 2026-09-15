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

    # Default should format as MID_DAY
    msg = format_signal_message(sig)

    # Verify header & ticker info
    assert "MID-DAY MOMENTUM" in msg
    assert "*BBRI* (Bank Rakyat Indonesia)" in msg
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


def test_contextual_telegram_templates():
    from models.scan_context import ScanContext

    sig = SignalPayload(
        ticker="ASII",
        company_name="Astra International",
        setup_type="BREAKOUT",
        parameters=TradingParameters(
            entry=5100.0,
            stop_loss=4950.0,
            take_profit_1=5400.0,
            take_profit_2=5700.0,
            rrr=2.0,
        ),
        metrics=SignalMetrics(
            rsi=55.0,
            volume_multiplier=1.7,
            foreign_accum_rank="ACCUM",
            broker_accum_rank="BIG_ACCUM",
        ),
        ai_context="Kinerja otomotif membaik.",
        scan_date="2026-09-15",
    )

    # Pre-market template
    msg_pre = format_signal_message(sig, context=ScanContext.PRE_MARKET)
    assert "🌅 *PRE-MARKET WATCHLIST*" in msg_pre
    assert "D-1 Closing" in msg_pre
    assert "RENCANA ENTRY HARI INI" in msg_pre
    assert "INDIKATOR D-1" in msg_pre

    # End-market template
    msg_end = format_signal_message(sig, context=ScanContext.END_MARKET)
    assert "🌙 *SWING WATCHLIST* — Entry Besok" in msg_end
    assert "EOD Closing Confirmed" in msg_end
    assert "RENCANA SWING BESOK" in msg_end
    assert "INDIKATOR EOD HARI INI" in msg_end
