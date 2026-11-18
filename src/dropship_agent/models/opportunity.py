"""
Product Opportunity models.

Two types
---------
OpportunityInput
    Carries the pre-computed outputs of the three upstream modules plus
    the operator-supplied selling price.  The evaluator combines these;
    it does not re-run any upstream service.

OpportunityResult
    The evaluated output: individual sub-scores, an overall score,
    a classification, and a plain-English narrative (strengths,
    weaknesses, risks, missing information, recommendation basis).

Design rules
------------
- None always means "not set / not available".  The evaluator never
  invents a default value for a missing input.
- data_verified reflects whether the upstream research was verified.
- No purchasing, payment, inventory, fulfilment or dispatch fields.
- All costs are in USD.  Currency mismatches are flagged, not silently fixed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .research import ResearchResult
from .supplier import SupplierComparisonResult


# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------

@dataclass
class OpportunityInput:
    """
    Input to ProductOpportunityEvaluator.evaluate().

    Fields
    ------
    product_id
        Matches Product.id — the link back to the persistent product record.

    research_result
        Output of ProductResearcher.evaluate().  None means market research
        has not been completed.

    supplier_comparison
        Output of SupplierResearcher.compare().  None means no suppliers
        have been researched.

    selling_price_usd
        The price at which the operator intends to list the product, in USD.
        None means no selling price has been set yet.  The evaluator will
        flag this as missing and return INSUFFICIENT DATA for the overall
        classification rather than assume a price.

    other_costs_usd
        Platform/operator costs that we control: listing fees, payment
        processing fees, packaging materials, etc.  These are distinct from
        the supplier's fulfilment costs, which are captured in the supplier
        research.  Defaults to 0.0.

    currency
        The currency in which selling_price_usd and other_costs_usd are
        denominated.  Must be "USD" for pricing calculations to proceed.

    data_verified
        True only if all upstream inputs have been verified against live
        sources.  Defaults to False.
    """
    product_id: str

    research_result: Optional[ResearchResult] = None
    supplier_comparison: Optional[SupplierComparisonResult] = None

    selling_price_usd: Optional[float] = None
    other_costs_usd: float = 0.0
    currency: str = "USD"
    data_verified: bool = False


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

@dataclass
class OpportunityResult:
    """
    Output of ProductOpportunityEvaluator.evaluate().

    Sub-scores
    ----------
    market_score   : 0–100.  Taken directly from ResearchResult.opportunity_score.
    supplier_score : 0–100.  Best non-disqualified SupplierEvaluation.overall_score.
    pricing_score  : 0–100.  Continuous: min(100, max(0, (margin_pct / 50) * 100)).

    overall_score  : Weighted composite of the three sub-scores (0–100).

    classification
        "STRONG"            overall_score >= 70
        "MODERATE"          overall_score >= 55
        "WEAK"              overall_score >= 40
        "POOR"              overall_score >= 1
        "INSUFFICIENT DATA" any essential input was missing

    Pricing detail (from calculate_pricing — not recomputed here)
    ---------------------------------------------------------------
    supplier_cost_usd      : best_unit_cost_usd from SupplierComparisonResult.
    estimated_margin_pct   : gross_margin_pct from PricingResult; None if
                             pricing could not be calculated.
    is_viable              : from PricingResult.is_viable; None if not calculated.

    Narrative
    ---------
    strengths              : factual bullets derived from high sub-scores.
    weaknesses             : factual bullets derived from low sub-scores.
    risks                  : structural risks (currency, single supplier, etc.).
    missing_information    : names of all missing fields gathered from upstream.
    recommendation_basis   : one plain-English sentence explaining the classification.

    Transparency
    ------------
    data_verified          : reflects whether upstream inputs were verified.
    """
    product_id: str

    # Sub-scores
    market_score: float
    supplier_score: float
    pricing_score: float
    overall_score: float

    # Classification
    classification: str

    # Pricing detail
    supplier_cost_usd: Optional[float]
    estimated_margin_pct: Optional[float]
    is_viable: Optional[bool]

    # Narrative
    strengths: list = field(default_factory=list)
    weaknesses: list = field(default_factory=list)
    risks: list = field(default_factory=list)
    missing_information: list = field(default_factory=list)
    recommendation_basis: str = ""

    # Transparency
    data_verified: bool = False
