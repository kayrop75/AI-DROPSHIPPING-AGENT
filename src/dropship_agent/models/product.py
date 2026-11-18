"""
Product data model.

This defines what a "product" means to the agent.
Every other module — researcher, analyst, pricing engine — works with this structure.

Scores (demand_score, competition_score) run from 0 to 100.
Costs and prices are in USD.
"""

from enum import Enum
from typing import Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field, computed_field
import uuid


class ProductStatus(str, Enum):
    """
    Tracks where a product is in the workflow.

    DISCOVERED    → agent found it, nothing evaluated yet
    RESEARCHING   → analysis is in progress
    UNDER_REVIEW  → waiting for human approval
    APPROVED      → approved for listing
    REJECTED      → not worth pursuing
    """
    DISCOVERED   = "DISCOVERED"
    RESEARCHING  = "RESEARCHING"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED     = "APPROVED"
    REJECTED     = "REJECTED"


class Product(BaseModel):
    """
    A product the agent is researching.

    All costs are in USD. Scores are 0–100 or None if not yet evaluated.
    """

    # Identity
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: str = ""
    category: str = ""

    # Supplier
    supplier_name: str = ""
    supplier_url: str = ""
    supplier_cost: float = Field(ge=0.0, description="What the supplier charges, in USD")

    # Costs
    shipping_cost: float = Field(default=0.0, ge=0.0, description="Shipping to customer, in USD")
    other_costs: float  = Field(default=0.0, ge=0.0, description="Packaging, fees, etc., in USD")

    # Pricing
    selling_price: float = Field(ge=0.0, description="Our intended selling price, in USD")

    # Research scores — None means not evaluated yet. Range: 0–100.
    demand_score:      Optional[float] = Field(default=None, ge=0.0, le=100.0)
    competition_score: Optional[float] = Field(default=None, ge=0.0, le=100.0)

    # Evidence gathered during research
    research_sources: list[str] = Field(default_factory=list)

    # Workflow state
    status: ProductStatus = ProductStatus.DISCOVERED

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # --- Calculated fields (read-only, derived from costs) ---

    @computed_field  # type: ignore[misc]
    @property
    def total_cost(self) -> float:
        """Sum of all costs before selling."""
        return round(self.supplier_cost + self.shipping_cost + self.other_costs, 2)

    @computed_field  # type: ignore[misc]
    @property
    def gross_profit(self) -> float:
        """Revenue minus all costs. Can be negative."""
        return round(self.selling_price - self.total_cost, 2)

    @computed_field  # type: ignore[misc]
    @property
    def gross_margin_pct(self) -> float:
        """
        Gross profit as a percentage of selling price.

        Note: this is gross margin only.
        It does NOT account for advertising, payment processing, refunds, or taxes.
        Those reduce your real net margin significantly.
        """
        if self.selling_price <= 0:
            return 0.0
        return round((self.gross_profit / self.selling_price) * 100, 2)

    @computed_field  # type: ignore[misc]
    @property
    def is_profitable(self) -> bool:
        """True if gross profit is positive. Use as a quick filter only."""
        return self.gross_profit > 0

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "Rechargeable LED Lantern",
                "category": "Home & Outdoors",
                "supplier_name": "AliExpress Supplier",
                "supplier_url": "https://aliexpress.com/item/example",
                "supplier_cost": 8.00,
                "shipping_cost": 2.00,
                "other_costs": 0.00,
                "selling_price": 22.00,
            }
        }
    }
