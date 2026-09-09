from models.signal import SignalPayload

OFFICIAL_OJK_DISCLAIMER = (
    "Analisis ini digenerasi secara otonom oleh bot komputasi untuk tujuan riset dan pencatatan pribadi. "
    "Bukan merupakan nasihat keuangan atau ajakan jual-beli efek sebagaimana diatur dalam regulasi OJK. "
    "Risiko investasi ditanggung sepenuhnya oleh masing-masing pelaku pasar."
)


def format_signal_message(signal: SignalPayload) -> str:
    """
    Renders the exact Markdown notification template specified in DOCS.md §3.5.
    """
    p = signal.parameters
    m = signal.metrics

    company_display = f" ({signal.company_name})" if signal.company_name else ""

    message = (
        f"🚨 *IDX STOCK RADAR - NEW SIGNAL* 🚨\n\n"
        f"*Ticker:* {signal.ticker}{company_display}\n"
        f"*Setup Type:* {signal.setup_type}\n\n"
        f"📈 *TRADING PLAN*\n"
        f"• *Entry Price:* Rp{p.entry:,.0f}\n"
        f"• *Stop Loss:* Rp{p.stop_loss:,.0f}\n"
        f"• *Take Profit 1:* Rp{p.take_profit_1:,.0f}\n"
        f"• *Take Profit 2:* Rp{p.take_profit_2:,.0f}\n"
        f"• *Risk-to-Reward Ratio (RRR):* 1:{p.rrr:.1f}\n\n"
        f"📊 *METRICS & ANALYSIS*\n"
        f"• *RSI (14):* {m.rsi:.1f}\n"
        f"• *Volume Multiplier:* {m.volume_multiplier:.1f}x (vs Rata-rata 20 Hari)\n"
        f"• *Foreign Flow:* {m.foreign_accum_rank}\n"
        f"• *Broker Flow (Bandarmologi):* {m.broker_accum_rank}\n\n"
        f"🤖 *AI SENTIMENT CONTEXT*\n"
        f'"{signal.ai_context}"\n\n'
        f"⚠️ *DISCLAIMER ON*\n"
        f"_{OFFICIAL_OJK_DISCLAIMER}_"
    )
    return message
