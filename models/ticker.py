from datetime import datetime
from typing import List, Literal, Optional
from pydantic import BaseModel, Field


BoardType = Literal["UTAMA", "PENGEMBANGAN", "AKSELERASI", "FCA", "UNKNOWN"]
BrokerAccumRank = Literal[
    "BIG_ACCUM",
    "SMALL_ACCUM",
    "NEUTRAL",
    "SMALL_DIST",
    "BIG_DIST",
    "DATA_N/A",
]
ForeignFlowRank = Literal["HIGH_ACCUM", "ACCUM", "NEUTRAL", "DIST", "HIGH_DIST", "DATA_N/A"]


class Ticker(BaseModel):
    symbol: str = Field(..., description="Stock code, e.g. BBCA.JK or BBCA")
    company_name: str = Field(default="", description="Full company name")
    board: BoardType = Field(default="UTAMA", description="Listing board on IDX")
    is_active: bool = Field(default=True, description="Active status on IDX")
    is_suspended: bool = Field(default=False, description="Suspension notation flag")
    avg_turnover_20d: float = Field(default=0.0, description="20-day average daily turnover in IDR")

    @property
    def clean_symbol(self) -> str:
        """Returns uppercase symbol without .JK suffix."""
        return self.symbol.upper().replace(".JK", "")

    @property
    def yf_symbol(self) -> str:
        """Returns symbol with .JK suffix for Yahoo Finance."""
        clean = self.clean_symbol
        return f"{clean}.JK"


class MarketDataRecord(BaseModel):
    time: datetime
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    turnover: float


class BrokerItem(BaseModel):
    broker_code: str
    volume: int
    value: float


class BrokerSummary(BaseModel):
    symbol: str
    date: str
    total_volume: int
    top3_buyers: List[BrokerItem] = Field(default_factory=list)
    top3_sellers: List[BrokerItem] = Field(default_factory=list)
    top3_net_buy_volume: int = 0
    top3_accumulation_ratio: float = 0.0  # (top3_buy_vol - top3_sell_vol) / total_vol
    accum_rank: BrokerAccumRank = "NEUTRAL"
    foreign_accum_rank: ForeignFlowRank = "NEUTRAL"
