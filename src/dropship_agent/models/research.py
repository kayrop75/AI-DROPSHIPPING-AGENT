from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ProductResearch:
    product_id: str
    demand_score: Optional[float] = None
    competition_score: Optional[float] = None
    trend_score: Optional[float] = None
    data_verified: bool = False


@dataclass
class ResearchResult:
    product_id: str
    opportunity_score: float
    rating: str
    data_verified: bool
    missing_fields: list = field(default_factory=list)
