from datetime import datetime, timezone
from typing import Literal, Optional
from uuid import uuid4
from pydantic import BaseModel, Field


SetupType = Literal[
    "BREAKOUT",
    "PULLBACK_REBOUND",
    "OVERSOLD_BOUNCE",
    "VOLUME_SURGE",
]


class TradingParameters(BaseModel):
    entry: float = Field(..., description="Calculated Entry price rounded to valid tick size")
    stop_loss: float = Field(..., description="Stop Loss price rounded to valid tick size")
    take_profit_1: float = Field(..., description="Target 1 price (minimum 1:2 RRR)")
    take_profit_2: float = Field(..., description="Target 2 price (minimum 1:3 RRR)")
    rrr: float = Field(..., description="Calculated Risk-to-Reward Ratio (TP1 - Entry) / (Entry - SL)")


class SignalMetrics(BaseModel):
    rsi: float = Field(..., description="14-period RSI value")
    volume_multiplier: float = Field(..., description="Intraday vs 20-day average volume multiplier")
    foreign_accum_rank: str = Field(default="NEUTRAL", description="Foreign flow ranking")
    broker_accum_rank: str = Field(..., description="Bandarmologi accumulation category")


class SignalPayload(BaseModel):
    signal_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).astimezone().isoformat()
    )
    ticker: str = Field(..., description="Stock symbol, e.g. BBRI")
    company_name: str = Field(default="", description="Registered company name")
    setup_type: SetupType = Field(..., description="Identified technical setup pattern")
    parameters: TradingParameters
    metrics: SignalMetrics
    ai_context: str = Field(..., description="AI sentiment analysis summary or reason")
