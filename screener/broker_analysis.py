from typing import List, Tuple
from models.ticker import BrokerAccumRank, BrokerItem, BrokerSummary


def classify_accumulation_ratio(ratio: float) -> BrokerAccumRank:
    """Classifies accumulation rank based on top 3 net volume ratio."""
    if ratio >= 0.20:
        return "BIG_ACCUM"
    elif ratio >= 0.05:
        return "SMALL_ACCUM"
    elif ratio > -0.05:
        return "NEUTRAL"
    elif ratio > -0.20:
        return "SMALL_DIST"
    else:
        return "BIG_DIST"


def analyze_broker_flow(
    symbol: str,
    date_str: str,
    total_volume: int,
    top_buyers: List[BrokerItem],
    top_sellers: List[BrokerItem],
    foreign_net_buy: float = 0.0,
) -> BrokerSummary:
    """
    Computes accumulation ratio and categorizes bandarmologi flow.
    """
    if total_volume <= 0:
        return BrokerSummary(
            symbol=symbol,
            date=date_str,
            total_volume=0,
            accum_rank="NEUTRAL",
            foreign_accum_rank="NEUTRAL",
        )

    # Sum top 3 buyer volumes
    top3_buy_vol = sum(b.volume for b in top_buyers[:3])
    # Sum top 3 seller volumes
    top3_sell_vol = sum(s.volume for s in top_sellers[:3])

    net_vol = top3_buy_vol - top3_sell_vol
    accum_ratio = round(net_vol / total_volume, 4)
    rank = classify_accumulation_ratio(accum_ratio)

    # Classify foreign flow
    if foreign_net_buy > 5_000_000_000:
        foreign_rank = "HIGH_ACCUM"
    elif foreign_net_buy > 500_000_000:
        foreign_rank = "ACCUM"
    elif foreign_net_buy < -5_000_000_000:
        foreign_rank = "HIGH_DIST"
    elif foreign_net_buy < -500_000_000:
        foreign_rank = "DIST"
    else:
        foreign_rank = "NEUTRAL"

    return BrokerSummary(
        symbol=symbol,
        date=date_str,
        total_volume=total_volume,
        top3_buyers=top_buyers[:3],
        top3_sellers=top_sellers[:3],
        top3_net_buy_volume=net_vol,
        top3_accumulation_ratio=accum_ratio,
        accum_rank=rank,
        foreign_accum_rank=foreign_rank,
    )
