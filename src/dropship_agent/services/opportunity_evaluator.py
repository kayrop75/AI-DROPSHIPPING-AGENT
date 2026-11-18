"""
Product Opportunity Evaluator service.

Responsibilities
----------------
- Combine the outputs of ProductResearcher, SupplierResearcher and the
  Pricing Engine into a single, scored opportunity assessment.
- Assign transparent sub-scores for market, supplier and pricing dimensions.
- Produce a classification and plain-English narrative.
- Flag every missing, estimated or unverified input.
- Never recompute what upstream services already calculated.
- Never fabricate scores from absent data.
- Never pass non-USD costs into the Pricing Engine.
- Never execute purchases, payments or fulfilment operations.

Scoring
-------
market_score (0–100)
    Taken directly from ResearchResult.opportunity_score.
    0 when research_result is None or rating is "INSUFFICIENT DATA".

supplier_score (0–100)
    The overall_score of the top non-disqualified SupplierEvaluation in
    SupplierComparisonResult.ranked_evaluations.
    0 when supplier_comparison is None or no qualified supplier exists.

pricing_score (0–100)
    Continuous formula applied to PricingResult.gross_margin_pct:
        pricing_score = min(100, max(0, (margin_pct / 50) * 100))
    A 50% margin scores 100; a 0% margin scores 0; negative margins score 0.
    0 when selling_price_usd is None, supplier cost is unknown,
    or currency is not USD.

overall_score (0–100)
    Weighted composite:
        overall = market * w_market + supplier * w_supplier + pricing * w_pricing

Classification
    overall_score >= 70  →  "STRONG"
    overall_score >= 55  →  "MODERATE"
    overall_score >= 40  →  "WEAK"
    overall_score >= 1   →  "POOR"
    essential input missing  →  "INSUFFICIENT DATA"

Essential inputs (all three required for a classification other than INSUFFICIENT DATA):
    - research_result present and not "INSUFFICIENT DATA"
    - at least one qualified (non-disqualified) supplier
    - selling_price_usd is not None and > 0
    - currency is "USD"
"""

from __future__ import annotations

from typing import Optional

from ..models.opportunity import OpportunityInput, OpportunityResult
from ..models.supplier import SupplierEvaluation
from .pricing import calculate_pricing, PricingResult


class ProductOpportunityEvaluator:
    """
    Combines market research, supplier intelligence and pricing analysis
    into a single opportunity assessment.

    Parameters
    ----------
    weights : dict, optional
        Keys: "market", "supplier", "pricing".
        Values must sum to 1.0 and be non-negative.
        Defaults to {"market": 0.40, "supplier": 0.35, "pricing": 0.25}.
    """

    DEFAULT_WEIGHTS: dict[str, float] = {
        "market":   0.40,
        "supplier": 0.35,
        "pricing":  0.25,
    }

    REQUIRED_WEIGHT_KEYS = frozenset(DEFAULT_WEIGHTS.keys())

    def __init__(self, weights: dict | None = None) -> None:
        self.weights = weights or dict(self.DEFAULT_WEIGHTS)
        self._validate_weights()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(self, inp: OpportunityInput) -> OpportunityResult:
        """
        Evaluate the opportunity represented by `inp`.

        Returns an OpportunityResult with all sub-scores, an overall score,
        a classification, and a full narrative.
        """
        missing: list[str] = []
        risks: list[str]   = []

        # --- Currency guard ---
        currency_ok = (inp.currency.upper() == "USD")
        if not currency_ok:
            risks.append(
                f"Currency is '{inp.currency}', not USD. "
                "Pricing calculations cannot proceed until costs are in USD."
            )

        # --- Market score ---
        market_score, market_missing = self._market_score(inp)
        missing.extend(market_missing)

        # --- Supplier score ---
        supplier_score, best_supplier_eval, supplier_missing = self._supplier_score(inp)
        missing.extend(supplier_missing)

        # Gather supplier cost for pricing
        supplier_cost_usd: Optional[float] = (
            inp.supplier_comparison.best_unit_cost_usd
            if inp.supplier_comparison is not None
            else None
        )

        # --- Pricing score ---
        pricing_score, pricing_result, pricing_missing, pricing_risks = (
            self._pricing_score(inp, supplier_cost_usd, currency_ok)
        )
        missing.extend(pricing_missing)
        risks.extend(pricing_risks)

        # --- Determine whether essential inputs are present ---
        essential_missing = self._essential_missing(
            inp, market_score, supplier_score, supplier_cost_usd, currency_ok
        )

        # --- Overall score ---
        overall_score = round(
            market_score   * self.weights["market"]
            + supplier_score * self.weights["supplier"]
            + pricing_score  * self.weights["pricing"],
            2,
        )

        # --- Classification ---
        if essential_missing:
            classification = "INSUFFICIENT DATA"
        else:
            classification = self._classify(overall_score)

        # --- Narrative ---
        strengths, weaknesses = self._narrative(
            market_score, supplier_score, pricing_score,
            pricing_result, inp, best_supplier_eval
        )

        # Single-supplier risk note
        if (
            inp.supplier_comparison is not None
            and inp.supplier_comparison.ranked_evaluations
        ):
            qualified = [
                e for e in inp.supplier_comparison.ranked_evaluations
                if not e.disqualified
            ]
            if len(qualified) == 1:
                risks.append(
                    "Only one qualified supplier available. "
                    "Consider researching additional suppliers to reduce dependency."
                )

        # Recommendation basis
        basis = self._recommendation_basis(
            classification, overall_score,
            market_score, supplier_score, pricing_score, missing
        )

        # Pricing detail
        estimated_margin_pct = (
            pricing_result.gross_margin_pct if pricing_result is not None else None
        )
        is_viable = (
            pricing_result.is_viable if pricing_result is not None else None
        )

        return OpportunityResult(
            product_id=inp.product_id,
            market_score=round(market_score, 2),
            supplier_score=round(supplier_score, 2),
            pricing_score=round(pricing_score, 2),
            overall_score=overall_score,
            classification=classification,
            supplier_cost_usd=supplier_cost_usd,
            estimated_margin_pct=estimated_margin_pct,
            is_viable=is_viable,
            strengths=strengths,
            weaknesses=weaknesses,
            risks=risks,
            missing_information=missing,
            recommendation_basis=basis,
            data_verified=inp.data_verified,
        )

    # ------------------------------------------------------------------
    # Sub-score helpers
    # ------------------------------------------------------------------

    def _market_score(
        self, inp: OpportunityInput
    ) -> tuple[float, list[str]]:
        """
        Returns (market_score 0–100, missing field names).
        Score taken directly from ResearchResult.opportunity_score.
        """
        missing: list[str] = []

        if inp.research_result is None:
            missing.append("research_result")
            return 0.0, missing

        if inp.research_result.rating == "INSUFFICIENT DATA":
            missing.extend(inp.research_result.missing_fields)
            return 0.0, missing

        return inp.research_result.opportunity_score, missing

    def _supplier_score(
        self, inp: OpportunityInput
    ) -> tuple[float, Optional[SupplierEvaluation], list[str]]:
        """
        Returns (supplier_score 0–100, best SupplierEvaluation or None, missing).
        Score taken from the top non-disqualified SupplierEvaluation.
        """
        missing: list[str] = []

        if inp.supplier_comparison is None:
            missing.append("supplier_comparison")
            return 0.0, None, missing

        qualified = [
            e for e in inp.supplier_comparison.ranked_evaluations
            if not e.disqualified
        ]

        if not qualified:
            missing.append("qualified_supplier")
            return 0.0, None, missing

        best = qualified[0]

        if best.recommendation == "INSUFFICIENT DATA":
            # Supplier exists but has no evaluable data
            missing.extend(best.missing_fields)
            return 0.0, best, missing

        return best.overall_score, best, missing

    def _pricing_score(
        self,
        inp: OpportunityInput,
        supplier_cost_usd: Optional[float],
        currency_ok: bool,
    ) -> tuple[float, Optional[PricingResult], list[str], list[str]]:
        """
        Returns (pricing_score 0–100, PricingResult or None, missing, risks).
        Calls calculate_pricing() once; does not reimplement the logic.
        """
        missing: list[str] = []
        risks: list[str]   = []

        if not currency_ok:
            missing.append("selling_price_usd (non-USD currency)")
            return 0.0, None, missing, risks

        if inp.selling_price_usd is None:
            missing.append("selling_price_usd")
            return 0.0, None, missing, risks

        if inp.selling_price_usd <= 0:
            risks.append(
                f"selling_price_usd must be > 0, got {inp.selling_price_usd}."
            )
            return 0.0, None, missing, risks

        if supplier_cost_usd is None:
            missing.append("supplier_cost_usd")
            return 0.0, None, missing, risks

        # other_costs_usd validation
        if inp.other_costs_usd < 0:
            risks.append(
                f"other_costs_usd cannot be negative, got {inp.other_costs_usd}."
            )
            return 0.0, None, missing, risks

        try:
            pricing_result = calculate_pricing(
                supplier_cost=supplier_cost_usd,
                shipping_cost=0.0,       # shipping already factored into supplier cost
                other_costs=inp.other_costs_usd,
                selling_price=inp.selling_price_usd,
            )
        except ValueError as exc:
            risks.append(f"Pricing calculation failed: {exc}")
            return 0.0, None, missing, risks

        margin_pct = pricing_result.gross_margin_pct
        score = min(100.0, max(0.0, (margin_pct / 50.0) * 100.0))

        if not pricing_result.is_viable:
            risks.append(
                f"Gross margin is {margin_pct:.2f}% — product is not viable "
                "at the current cost and selling price."
            )

        return score, pricing_result, missing, risks

    # ------------------------------------------------------------------
    # Essential-inputs check
    # ------------------------------------------------------------------

    @staticmethod
    def _essential_missing(
        inp: OpportunityInput,
        market_score: float,
        supplier_score: float,
        supplier_cost_usd: Optional[float],
        currency_ok: bool,
    ) -> bool:
        """
        Returns True if the overall classification must be INSUFFICIENT DATA.

        Rules (any one triggers it):
          - research_result is None
          - research_result.rating == "INSUFFICIENT DATA"
          - no qualified supplier (supplier_score == 0 and supplier_comparison exists
            but has no qualified entries, OR supplier_comparison is None)
          - selling_price_usd is None or <= 0
          - currency is not USD
          - supplier cost is unknown
        """
        if inp.research_result is None:
            return True
        if inp.research_result.rating == "INSUFFICIENT DATA":
            return True
        if inp.supplier_comparison is None:
            return True
        qualified = [
            e for e in inp.supplier_comparison.ranked_evaluations
            if not e.disqualified
        ]
        if not qualified:
            return True
        if inp.selling_price_usd is None or inp.selling_price_usd <= 0:
            return True
        if not currency_ok:
            return True
        if supplier_cost_usd is None:
            return True
        return False

    # ------------------------------------------------------------------
    # Classification
    # ------------------------------------------------------------------

    @staticmethod
    def _classify(overall_score: float) -> str:
        if overall_score >= 70.0:
            return "STRONG"
        if overall_score >= 55.0:
            return "MODERATE"
        if overall_score >= 40.0:
            return "WEAK"
        return "POOR"

    # ------------------------------------------------------------------
    # Narrative
    # ------------------------------------------------------------------

    def _narrative(
        self,
        market_score: float,
        supplier_score: float,
        pricing_score: float,
        pricing_result: Optional[PricingResult],
        inp: OpportunityInput,
        best_supplier: Optional[SupplierEvaluation],
    ) -> tuple[list[str], list[str]]:
        """
        Build factual strength and weakness bullets from sub-scores.
        Uses specific numbers, not vague language.
        """
        strengths: list[str] = []
        weaknesses: list[str] = []

        # Market
        if inp.research_result is not None and inp.research_result.rating != "INSUFFICIENT DATA":
            label = inp.research_result.rating
            if market_score >= 70:
                strengths.append(
                    f"Market opportunity score: {market_score:.1f}/100 — {label}."
                )
            elif market_score >= 40:
                weaknesses.append(
                    f"Market opportunity score: {market_score:.1f}/100 — {label}."
                )
            else:
                weaknesses.append(
                    f"Market opportunity score: {market_score:.1f}/100 — {label}. "
                    "Low demand or high competition detected."
                )

        # Supplier
        if best_supplier is not None and not best_supplier.recommendation == "INSUFFICIENT DATA":
            rec = best_supplier.recommendation
            if supplier_score >= 70:
                strengths.append(
                    f"Best supplier score: {supplier_score:.1f}/100 — {rec}."
                )
            elif supplier_score >= 50:
                weaknesses.append(
                    f"Best supplier score: {supplier_score:.1f}/100 — {rec}. "
                    "Supplier quality acceptable but not strong."
                )
            else:
                weaknesses.append(
                    f"Best supplier score: {supplier_score:.1f}/100 — {rec}. "
                    "Supplier quality is low; consider researching alternatives."
                )

        # Pricing
        if pricing_result is not None:
            margin = pricing_result.gross_margin_pct
            if margin >= 40:
                strengths.append(
                    f"Gross margin: {margin:.2f}% — strong pricing opportunity."
                )
            elif margin >= 20:
                weaknesses.append(
                    f"Gross margin: {margin:.2f}% — moderate; leaves limited room "
                    "for advertising and returns."
                )
            else:
                weaknesses.append(
                    f"Gross margin: {margin:.2f}% — low; product may not be "
                    "viable once advertising and fees are included."
                )
        else:
            weaknesses.append("Pricing could not be calculated — selling price or supplier cost missing.")

        return strengths, weaknesses

    # ------------------------------------------------------------------
    # Recommendation basis
    # ------------------------------------------------------------------

    @staticmethod
    def _recommendation_basis(
        classification: str,
        overall_score: float,
        market_score: float,
        supplier_score: float,
        pricing_score: float,
        missing: list[str],
    ) -> str:
        if classification == "INSUFFICIENT DATA":
            missing_str = ", ".join(missing) if missing else "unknown inputs"
            return (
                f"Classification is INSUFFICIENT DATA because required "
                f"information is missing: {missing_str}."
            )
        return (
            f"Overall score {overall_score:.1f}/100 ({classification}) based on "
            f"market score {market_score:.1f}, "
            f"supplier score {supplier_score:.1f}, "
            f"pricing score {pricing_score:.1f}."
        )

    # ------------------------------------------------------------------
    # Weight validation
    # ------------------------------------------------------------------

    def _validate_weights(self) -> None:
        if set(self.weights.keys()) != self.REQUIRED_WEIGHT_KEYS:
            raise ValueError(
                f"weights must have exactly these keys: "
                f"{sorted(self.REQUIRED_WEIGHT_KEYS)}"
            )
        if any(w < 0 for w in self.weights.values()):
            raise ValueError("Opportunity evaluator weights cannot be negative.")
        if abs(sum(self.weights.values()) - 1.0) > 1e-6:
            raise ValueError("Opportunity evaluator weights must total 1.0.")
