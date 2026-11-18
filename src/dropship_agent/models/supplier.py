"""
Supplier data models for the AI Dropshipping Agent.

Three layers
------------
Supplier
    The persistent record for a known supplier.  Pydantic BaseModel so that
    Pydantic validates every field on construction, matching the Product model
    convention.

SupplierResearch
    A lightweight dataclass that carries the evidence we have gathered about
    one supplier, ready to pass into SupplierResearcher.evaluate().  Mirrors
    the ProductResearch / Product split in Step 3.

SupplierEvaluation
    The scored output for a single supplier.

SupplierComparisonResult
    The output of a full multi-supplier comparison for one product.

Design rules
------------
- None always means "not available / not verified".  We never substitute a
  plausible-sounding default for real missing data.
- data_verified=False is the safe default.  It must be set to True only by
  code that has actually checked the information against a live source.
- Currency is recorded but conversion is out of scope.  The service enforces
  USD before passing costs into the Pricing Engine.
- Fulfilment responsibility belongs to the supplier.  None of these models
  record purchase orders, payment details or dispatch operations.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class AvailabilityStatus(str, Enum):
    """
    What we know about current stock at the time of research.
    UNKNOWN is the safe default — never assume IN_STOCK without evidence.
    """
    IN_STOCK     = "IN_STOCK"
    LOW_STOCK    = "LOW_STOCK"
    OUT_OF_STOCK = "OUT_OF_STOCK"
    UNKNOWN      = "UNKNOWN"


class FulfilmentType(str, Enum):
    """
    How the supplier delivers to the end customer.
    DROPSHIP means the supplier ships directly — this is our model.
    WHOLESALE is recorded for awareness but falls outside our business model.
    """
    DROPSHIP        = "DROPSHIP"
    WHOLESALE       = "WHOLESALE"
    PRINT_ON_DEMAND = "PRINT_ON_DEMAND"
    UNKNOWN         = "UNKNOWN"


class VerificationStatus(str, Enum):
    """
    How confident we are in a data point.
    Used in SupplierEvaluation to describe the quality of the evidence.
    """
    VERIFIED    = "VERIFIED"    # confirmed against a live/authoritative source
    ESTIMATED   = "ESTIMATED"   # inferred or extrapolated from partial data
    UNVERIFIED  = "UNVERIFIED"  # present but source not confirmed
    UNAVAILABLE = "UNAVAILABLE" # field simply not found


# ---------------------------------------------------------------------------
# Value object: ShippingOption
# ---------------------------------------------------------------------------

@dataclass
class ShippingOption:
    """
    One shipping method offered by a supplier.

    estimated_days_min / _max: delivery estimate in calendar days.
    cost_usd: shipping cost in USD; None when it varies or is unknown.
    tracked: whether the method provides a tracking number.
    verified: True only if this was confirmed from the supplier listing.
    """
    method: str
    estimated_days_min: Optional[int] = None
    estimated_days_max: Optional[int] = None
    cost_usd: Optional[float] = None
    tracked: Optional[bool] = None
    verified: bool = False


# ---------------------------------------------------------------------------
# Persistent record: Supplier
# ---------------------------------------------------------------------------

class Supplier(BaseModel):
    """
    A supplier discovered during research.

    All cost fields are in USD.  If a supplier quotes in another currency,
    record it in `currency` and leave unit_cost_usd as None until a proper
    conversion has been performed.

    We do not own inventory, store products, package, dispatch, ship or
    deliver.  Those responsibilities belong to the supplier.  This model
    records what we have researched about the supplier, not what we do.
    """

    # --- Identity ---
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(min_length=1)
    platform: str = Field(default="", description="e.g. AliExpress, CJ Dropshipping, Faire")
    source_url: str = Field(default="", description="Listing or profile URL — evidence only")
    contact_info: str = Field(default="", description="Optional email or chat reference")

    # --- Product link ---
    product_id: str = Field(min_length=1, description="Matches Product.id")
    product_name_on_platform: str = ""
    category: str = ""

    # --- Pricing ---
    unit_cost_usd: Optional[float] = Field(
        default=None,
        ge=0.0,
        description=(
            "What this supplier charges per unit in USD.  "
            "None if unknown or currency is not USD."
        ),
    )
    currency: str = Field(
        default="USD",
        description="Quoted currency. Only USD costs pass into the Pricing Engine.",
    )
    minimum_order_quantity: int = Field(
        default=1,
        ge=1,
        description="Minimum units per order.  1 = no minimum.",
    )

    # --- Availability ---
    availability: AvailabilityStatus = AvailabilityStatus.UNKNOWN
    stock_verified_at: Optional[datetime] = Field(
        default=None,
        description="When availability was last confirmed.  None = never verified.",
    )

    # --- Fulfilment ---
    fulfilment_type: FulfilmentType = FulfilmentType.UNKNOWN
    ships_from_country: str = ""
    ships_to_countries: list[str] = Field(default_factory=list)
    shipping_options: list[ShippingOption] = Field(default_factory=list)

    # --- Reliability evidence ---
    platform_rating: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=5.0,
        description="Supplier rating on their platform (0–5).  None = not available.",
    )
    review_count: Optional[int] = Field(
        default=None,
        ge=0,
        description="Number of reviews on the platform.  None = not available.",
    )
    years_active: Optional[int] = Field(
        default=None,
        ge=0,
        description="How long the supplier has been active.  None = not available.",
    )
    return_policy_available: Optional[bool] = Field(
        default=None,
        description="True if a return/refund policy exists.  None = unknown.",
    )
    return_policy_notes: str = ""

    # --- Verification ---
    data_verified: bool = False
    verified_at: Optional[datetime] = None

    # --- Timestamps ---
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "Example Supplier Co.",
                "platform": "AliExpress",
                "source_url": "https://aliexpress.com/store/example",
                "product_id": "some-product-uuid",
                "unit_cost_usd": 8.50,
                "minimum_order_quantity": 1,
                "availability": "IN_STOCK",
                "fulfilment_type": "DROPSHIP",
            }
        }
    }


# ---------------------------------------------------------------------------
# Input to the researcher: SupplierResearch
# ---------------------------------------------------------------------------

@dataclass
class SupplierResearch:
    """
    The evidence we have gathered about one supplier, ready for evaluation.

    This is the input type for SupplierResearcher.evaluate().  It is
    separate from Supplier (the persistent record) so that the researcher
    service does not depend on Pydantic and remains a pure data-in /
    data-out function.

    Every field is optional (None = not available).  The researcher will
    report missing fields rather than fabricate scores from absent data.

    cost_includes_shipping: True if unit_cost_usd already bundles shipping.
    """
    supplier_id: str

    # Pricing
    unit_cost_usd: Optional[float] = None
    currency: str = "USD"
    minimum_order_quantity: int = 1
    cost_includes_shipping: Optional[bool] = None

    # Availability
    availability: str = "UNKNOWN"       # maps to AvailabilityStatus values

    # Shipping evidence
    has_tracked_shipping: Optional[bool] = None
    min_delivery_days: Optional[int] = None
    max_delivery_days: Optional[int] = None
    shipping_cost_usd: Optional[float] = None

    # Reliability evidence
    platform_rating: Optional[float] = None   # 0–5
    review_count: Optional[int] = None
    years_active: Optional[int] = None
    return_policy_available: Optional[bool] = None

    # Fulfilment
    fulfilment_type: str = "UNKNOWN"    # maps to FulfilmentType values

    # Verification
    data_verified: bool = False


# ---------------------------------------------------------------------------
# Output: SupplierEvaluation
# ---------------------------------------------------------------------------

@dataclass
class SupplierEvaluation:
    """
    The scored result for one supplier.

    reliability_score : 0–100  — evidence of trustworthiness
    fulfilment_score  : 0–100  — shipping speed, tracking, returns
    cost_score        : 0–100  — relative to the comparison group
                                 (meaningless in isolation)
    overall_score     : weighted composite, 0–100

    disqualified      : True if a hard rule removed this supplier before
                        scoring (e.g. OUT_OF_STOCK, missing cost, non-USD).
    recommendation    : "RECOMMENDED" / "ACCEPTABLE" / "RISKY" /
                        "INSUFFICIENT DATA" / "DISQUALIFIED"

    missing_fields    : names of fields that were None and reduced the score
                        or prevented a full evaluation.
    cost_score_note   : human-readable explanation of the cost comparison,
                        including any caveats about shipping or MOQ.
    """
    supplier_id: str
    reliability_score: float
    fulfilment_score: float
    cost_score: float
    overall_score: float
    recommendation: str
    data_verified: bool
    missing_fields: list = field(default_factory=list)
    disqualified: bool = False
    disqualification_reason: str = ""
    cost_score_note: str = ""


# ---------------------------------------------------------------------------
# Output: SupplierComparisonResult
# ---------------------------------------------------------------------------

@dataclass
class SupplierComparisonResult:
    """
    The result of comparing multiple suppliers for one product.

    product_id              : the Product this comparison is for
    ranked_evaluations      : all SupplierEvaluations, best first
                              (disqualified suppliers always last)
    recommended_supplier_id : id of the top non-disqualified supplier,
                              or None if no supplier qualified
    best_unit_cost_usd      : unit cost of the recommended supplier,
                              suitable for passing to calculate_pricing()
                              — None if no qualified supplier has a known
                              USD cost
    comparison_notes        : list of plain-English observations about the
                              comparison (e.g. cost data gaps, single supplier)
    """
    product_id: str
    ranked_evaluations: list = field(default_factory=list)
    recommended_supplier_id: Optional[str] = None
    best_unit_cost_usd: Optional[float] = None
    comparison_notes: list = field(default_factory=list)
