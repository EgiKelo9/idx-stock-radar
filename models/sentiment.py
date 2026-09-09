from typing import List, Literal, Optional
from pydantic import BaseModel, Field


SentimentLabel = Literal["POSITIVE", "NEUTRAL", "NEGATIVE"]
CatalystEvent = Literal[
    "FINANCIAL_REPORT",
    "DIVIDEND_ANNOUNCEMENT",
    "CORPORATE_ACTION",
    "LEGAL_RISK",
    "MATERIAL_DISCLOSURE",
    "NONE",
]


class SentimentResult(BaseModel):
    ticker: str = Field(..., description="Stock ticker code without .JK suffix")
    sentiment_score: float = Field(
        ..., ge=-1.0, le=1.0, description="Normalized sentiment score from -1.0 to +1.0"
    )
    sentiment_label: SentimentLabel = Field(..., description="Categorical sentiment label")
    catalyst_event: CatalystEvent = Field(
        default="NONE", description="Categorized primary event driver"
    )
    summary: str = Field(..., description="Brief one-sentence context in Indonesian")
    risk_flags: List[str] = Field(
        default_factory=list, description="Specific risk warnings identified in disclosures"
    )

    @classmethod
    def neutral_fallback(cls, ticker: str, reason: str = "Tidak ada keterbukaan informasi terbaru atau analisis AI dilewati.") -> "SentimentResult":
        """Creates a neutral fallback sentiment result when LLM or disclosure is unavailable."""
        return cls(
            ticker=ticker,
            sentiment_score=0.0,
            sentiment_label="NEUTRAL",
            catalyst_event="NONE",
            summary=reason,
            risk_flags=[],
        )
