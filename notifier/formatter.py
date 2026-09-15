from typing import Optional
from models.scan_context import ScanContext
from models.signal import SignalPayload

OFFICIAL_OJK_DISCLAIMER = (
    "Analisis ini digenerasi secara otonom oleh bot komputasi untuk tujuan riset dan pencatatan pribadi. "
    "Bukan merupakan nasihat keuangan atau ajakan jual-beli efek sebagaimana diatur dalam regulasi OJK. "
    "Risiko investasi ditanggung sepenuhnya oleh masing-masing pelaku pasar."
)


def escape_markdown(text: str) -> str:
    """
    Escapes characters that have special meaning in Telegram legacy Markdown (v1):
    '_', '*', '`', '['
    """
    if not text:
        return ""
    for ch in ("_", "*", "`", "["):
        text = text.replace(ch, f"\\{ch}")
    return text


def format_signal_message(
    signal: SignalPayload,
    context: Optional[ScanContext] = None,
) -> str:
    """
    Renders contextual Telegram Markdown (v1) templates for:
    - PRE_MARKET: 🌅 PRE-MARKET WATCHLIST (D-1 settled data, plan for today)
    - MID_DAY: ☀️ MID-DAY MOMENTUM (Session 1 momentum, plan for Session 2)
    - END_MARKET: 🌙 SWING WATCHLIST — BESOK (EOD confirmed candles, swing plan for tomorrow)
    """
    if context is None:
        try:
            context = ScanContext(getattr(signal, "scan_context", "MID_DAY"))
        except ValueError:
            context = ScanContext.MID_DAY

    p = signal.parameters
    m = signal.metrics

    company_display = f" ({escape_markdown(signal.company_name)})" if signal.company_name else ""
    ticker_display = escape_markdown(signal.ticker)
    setup_type_display = escape_markdown(signal.setup_type)
    foreign_flow_display = escape_markdown(m.foreign_accum_rank)
    broker_flow_display = escape_markdown(m.broker_accum_rank)
    ai_context_display = escape_markdown(signal.ai_context)
    scan_date_display = escape_markdown(getattr(signal, "scan_date", ""))

    if context == ScanContext.PRE_MARKET:
        date_header = f" — {scan_date_display}" if scan_date_display else ""
        header = f"🌅 *PRE-MARKET WATCHLIST*{date_header}"
        setup_subtitle = f"Setup: {setup_type_display} (D-1 Closing)"
        plan_header = "🎯 *RENCANA ENTRY HARI INI*"
        metrics_header = "📊 *INDIKATOR D-1*"
        vol_label = "Volume vs 20D"
    elif context == ScanContext.END_MARKET:
        header = "🌙 *SWING WATCHLIST* — Entry Besok"
        setup_subtitle = f"Setup: {setup_type_display} (EOD Closing Confirmed)"
        plan_header = "🎯 *RENCANA SWING BESOK*"
        metrics_header = "📊 *INDIKATOR EOD HARI INI*"
        vol_label = "Volume vs 20D"
    else:  # MID_DAY default
        header = "☀️ *MID-DAY MOMENTUM* — Sesi 1 Selesai"
        setup_subtitle = f"Setup: {setup_type_display} (Sesi 1 Breakout)"
        plan_header = "🎯 *RENCANA ENTRY SESI 2*"
        metrics_header = "📊 *METRIK SESI 1*"
        vol_label = "Volume Sesi 1 vs Rata-rata 20D"

    message = (
        f"{header}\n\n"
        f"📌 *{ticker_display}*{company_display}\n"
        f"{setup_subtitle}\n\n"
        f"{plan_header}\n"
        f"  *Entry Price:* Rp{p.entry:,.0f}\n"
        f"  *Stop Loss:* Rp{p.stop_loss:,.0f}\n"
        f"  *Target 1:* Rp{p.take_profit_1:,.0f}  (RRR 1:{p.rrr:.1f})\n"
        f"  *Target 2:* Rp{p.take_profit_2:,.0f}\n\n"
        f"{metrics_header}\n"
        f"  *RSI (14):* {m.rsi:.1f}\n"
        f"  *{vol_label}:* {m.volume_multiplier:.1f}x\n"
        f"  *Foreign Flow:* {foreign_flow_display}\n"
        f"  *Broker Flow (Bandarmologi):* {broker_flow_display}\n\n"
        f"🤖 *AI SENTIMENT*\n"
        f'"{ai_context_display}"\n\n'
        f"⚠️ *DISCLAIMER ON*\n"
        f"_{OFFICIAL_OJK_DISCLAIMER}_"
    )
    return message
