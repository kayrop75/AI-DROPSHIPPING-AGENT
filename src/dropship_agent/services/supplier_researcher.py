"""
Supplier Researcher service.

Responsibilities
----------------
- Accept SupplierResearch inputs (evidence gathered about a supplier).
- Score each supplier across three transparent dimensions:
    reliability  — evidence of trustworthiness (rating, reviews, years active)
    fulfilment   — shipping capability (tracking, speed, return policy)
    cost         — relative to the comparison group
- Apply hard disqualification rules before scoring.
- Rank suppliers for a product and return a SupplierComparisonResult.
- Expose individual sub-scores alongside the overall score.
- Flag every missing or incomplete data point explicitly.
- Never fabricate scores from absent data.
- Never pass non-USD costs into the Pricing Engine.
- Never execute purchases, payments or fulfilment operations.

Scoring rules
-------------
Reliability sub-score (0–100):
    platform_rating (0–5)  → 0–60 pts  (linear: rating/5 × 60)
    review_count           → 0–20 pts  (log scale: min(log10(count+1)/4, 1) × 20)
    years_active           → 0–20 pts  (linear: min(years/10, 1) × 20)
    Missing field → that component contributes 0.  Noted in missing_fields.

Fulfilment sub-score (0–100):
    tracked shipping       → 40 pts (yes) / 0 (no) / 0 when unknown (conservative)
    delivery speed         → 40 pts: <7d=40, 7–14=25, 14–21=10, >21=0, unknown=0
    return policy          → 20 pts (available) / 0 (not available or unknown)

Cost sub-score (0–100):
    Relative within the comparison group.
    The supplier with the lowest comparable cost scores 100.
    Others are scaled: (min_cost / this_cost) × 100.
    "Comparable cost" = unit_cost_usd + shipping_cost_usd when both are
    available.  When shipping is bundled (cost_includes_shipping=True),
    unit_cost_usd is used directly.  When shipping cost is unknown, only
    unit_cost_usd is used but a note is added to cost_score_note.
    A supplier with no USD cost is disqualified before this calculation.

Disqualification rules (applied before scoring):
    1. unit_cost_usd is None             → cannot price
    2. unit_cost_usd <= 0                → invalid cost
    3. currency != "USD"                 → non-USD; guard for Pricing Engine
    4. availability == "OUT_OF_STOCK"    → cannot fulfil

Recommendation bands:
    overall_score >= 70  → "RECOMMENDED"
    overall_score >= 50  → "ACCEPTABLE"
    overall_score >= 1   → "RISKY"
    missing required fields → "INSUFFICIENT DATA"
    disqualified         → "DISQUALIFIED"
"""

from __future__ import annotations

import math
from typing import Optional

from ..models.supplier import (
    SupplierResearch,
    SupplierEvaluation,
    SupplierComparisonResult,
)


class SupplierResearcher:
    """
    Evaluates and ranks suppliers for a dropshipping product.

    Parameters
    ----------
    weights : dict, optional
        Keys: "reliability", "fulfilment", "cost".
        Values must sum to 1.0 and be non-negative.
        Defaults to {"reliability": 0.50, "fulfilment": 0.30, "cost": 0.20}.
    """

    DEFAULT_WEIGHTS: dict[str, float] = {
        "reliability": 0.50,
        "fulfilment":  0.30,
        "cost":        0.20,
    }

    REQUIRED_WEIGHT_KEYS = frozenset(DEFAULT_WEIGHTS.keys())

    def __init__(self, weights: dict | None = None) -> None:
        self.weights = weights or dict(self.DEFAULT_WEIGHTS)
        self._validate_weights()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(
        self,
        supplier: SupplierResearch,
        cost_score: float = 0.0,
        cost_score_note: str = "",
    ) -> SupplierEvaluation:
        """
        Score one supplier.

        cost_score and cost_score_note are normally supplied by compare()
        after it has computed relative costs across the full group.
        When evaluate() is called directly (e.g. in tests), cost_score
        defaults to 0.0 and cost_score_note is empty.

        Returns a SupplierEvaluation with all sub-scores populated.
        Disqualified suppliers receive overall_score=0 and
        recommendation="DISQUALIFIED".
        """
        # --- Hard disqualification ---
        disq_reason = self._disqualification_reason(supplier)
        if disq_reason:
            return SupplierEvaluation(
                supplier_id=supplier.supplier_id,
                reliability_score=0.0,
                fulfilment_score=0.0,
                cost_score=0.0,
                overall_score=0.0,
                recommendation="DISQUALIFIED",
                data_verified=supplier.data_verified,
                missing_fields=[],
                disqualified=True,
                disqualification_reason=disq_reason,
                cost_score_note="",
            )

        # --- Sub-scores ---
        reliability_score, reliability_missing = self._reliability_score(supplier)
        fulfilment_score,  fulfilment_missing  = self._fulfilment_score(supplier)

        missing_fields = reliability_missing + fulfilment_missing

        # If all three scoring dimensions have zero usable data, flag as
        # INSUFFICIENT DATA rather than returning a meaningless 0.
        all_missing = (
            supplier.platform_rating is None
            and supplier.review_count is None
            and supplier.years_active is None
            and supplier.has_tracked_shipping is None
            and supplier.min_delivery_days is None
            and supplier.return_policy_available is None
        )

        if all_missing:
            return SupplierEvaluation(
                supplier_id=supplier.supplier_id,
                reliability_score=0.0,
                fulfilment_score=0.0,
                cost_score=cost_score,
                overall_score=0.0,
                recommendation="INSUFFICIENT DATA",
                data_verified=supplier.data_verified,
                missing_fields=missing_fields,
                disqualified=False,
                disqualification_reason="",
                cost_score_note=cost_score_note,
            )

        # --- Overall score ---
        overall = round(
            reliability_score * self.weights["reliability"]
            + fulfilment_score  * self.weights["fulfilment"]
            + cost_score        * self.weights["cost"],
            2,
        )

        recommendation = self._recommendation(overall)

        return SupplierEvaluation(
            supplier_id=supplier.supplier_id,
            reliability_score=round(reliability_score, 2),
            fulfilment_score=round(fulfilment_score, 2),
            cost_score=round(cost_score, 2),
            overall_score=overall,
            recommendation=recommendation,
            data_verified=supplier.data_verified,
            missing_fields=missing_fields,
            disqualified=False,
            disqualification_reason="",
            cost_score_note=cost_score_note,
        )

    def compare(
        self,
        suppliers: list[SupplierResearch],
        product_id: str,
    ) -> SupplierComparisonResult:
        """
        Evaluate all suppliers for a product, compute relative cost scores,
        rank the results (highest overall_score first; disqualified last),
        and return a SupplierComparisonResult.
        """
        if not suppliers:
            return SupplierComparisonResult(
                product_id=product_id,
                ranked_evaluations=[],
                recommended_supplier_id=None,
                best_unit_cost_usd=None,
                comparison_notes=["No suppliers provided for comparison."],
            )

        notes: list[str] = []

        # --- Relative cost scores ---
        cost_scores, cost_notes = self._compute_cost_scores(suppliers, notes)

        # --- Evaluate each supplier ---
        evaluations: list[SupplierEvaluation] = []
        for s in suppliers:
            cs    = cost_scores.get(s.supplier_id, 0.0)
            cn    = cost_notes.get(s.supplier_id, "")
            evalu = self.evaluate(s, cost_score=cs, cost_score_note=cn)
            evaluations.append(evalu)

        # --- Rank: qualified by overall_score desc, disqualified last ---
        qualified    = [e for e in evaluations if not e.disqualified]
        disqualified = [e for e in evaluations if e.disqualified]

        qualified.sort(key=lambda e: e.overall_score, reverse=True)
        ranked = qualified + disqualified

        # --- Recommended supplier ---
        recommended_id:    Optional[str]   = None
        best_unit_cost:    Optional[float] = None

        for evalu in qualified:
            if evalu.recommendation in ("RECOMMENDED", "ACCEPTABLE"):
                recommended_id = evalu.supplier_id
                # Find the matching supplier to get its USD cost
                for s in suppliers:
                    if s.supplier_id == evalu.supplier_id and s.unit_cost_usd is not None:
                        best_unit_cost = s.unit_cost_usd
                break

        if len(suppliers) == 1:
            notes.append(
                "Only one supplier was provided. "
                "Cost score reflects no relative comparison."
            )

        if recommended_id is None and qualified:
            notes.append(
                "No supplier reached RECOMMENDED or ACCEPTABLE threshold. "
                "All qualified suppliers rated RISKY or INSUFFICIENT DATA."
            )

        return SupplierComparisonResult(
            product_id=product_id,
            ranked_evaluations=ranked,
            recommended_supplier_id=recommended_id,
            best_unit_cost_usd=best_unit_cost,
            comparison_notes=notes,
        )

    def rank_suppliers(
        self,
        suppliers: list[SupplierResearch],
    ) -> list[SupplierEvaluation]:
        """
        Evaluate and rank suppliers without a product context.
        Useful when only relative ranking is needed.
        Disqualified suppliers always appear last.
        """
        if not suppliers:
            return []
        result = self.compare(suppliers, product_id="__unset__")
        return result.ranked_evaluations

    # ------------------------------------------------------------------
    # Scoring helpers
    # ------------------------------------------------------------------

    def _reliability_score(
        self,
        s: SupplierResearch,
    ) -> tuple[float, list[str]]:
        """
        Returns (score 0–100, list of missing field names).

        Components:
            platform_rating  → 0–60 pts
            review_count     → 0–20 pts
            years_active     → 0–20 pts
        """
        score   = 0.0
        missing = []

        if s.platform_rating is not None:
            if not (0.0 <= s.platform_rating <= 5.0):
                raise ValueError(
                    f"platform_rating must be 0–5, got {s.platform_rating}"
                )
            score += (s.platform_rating / 5.0) * 60.0
        else:
            missing.append("platform_rating")

        if s.review_count is not None:
            if s.review_count < 0:
                raise ValueError(
                    f"review_count cannot be negative, got {s.review_count}"
                )
            # log10(1) = 0, log10(10001) ≈ 4 → cap at 4 → /4 → fraction → × 20
            score += (min(math.log10(s.review_count + 1) / 4.0, 1.0)) * 20.0
        else:
            missing.append("review_count")

        if s.years_active is not None:
            if s.years_active < 0:
                raise ValueError(
                    f"years_active cannot be negative, got {s.years_active}"
                )
            score += (min(s.years_active / 10.0, 1.0)) * 20.0
        else:
            missing.append("years_active")

        return score, missing

    def _fulfilment_score(
        self,
        s: SupplierResearch,
    ) -> tuple[float, list[str]]:
        """
        Returns (score 0–100, list of missing field names).

        Components:
            tracked shipping → 0 or 40 pts (conservative: unknown = 0)
            delivery speed   → 0–40 pts
            return policy    → 0 or 20 pts (conservative: unknown = 0)
        """
        score   = 0.0
        missing = []

        # Tracked shipping (conservative: unknown → 0, not partial credit)
        if s.has_tracked_shipping is True:
            score += 40.0
        elif s.has_tracked_shipping is None:
            missing.append("has_tracked_shipping")
        # False → 0, no missing entry (data present, just unfavourable)

        # Delivery speed — use max days as the representative figure
        if s.max_delivery_days is not None:
            if s.max_delivery_days < 0:
                raise ValueError(
                    f"max_delivery_days cannot be negative, got {s.max_delivery_days}"
                )
            if s.max_delivery_days < 7:
                score += 40.0
            elif s.max_delivery_days <= 14:
                score += 25.0
            elif s.max_delivery_days <= 21:
                score += 10.0
            # > 21 days → 0 pts
        else:
            missing.append("max_delivery_days")

        # Return policy (conservative: unknown → 0)
        if s.return_policy_available is True:
            score += 20.0
        elif s.return_policy_available is None:
            missing.append("return_policy_available")

        return score, missing

    def _compute_cost_scores(
        self,
        suppliers: list[SupplierResearch],
        notes: list[str],
    ) -> tuple[dict[str, float], dict[str, str]]:
        """
        Compute relative cost scores (0–100) across qualified suppliers.

        "Comparable cost" = unit_cost_usd + shipping_cost_usd when both
        are available and cost_includes_shipping is not True.
        When shipping is unknown, only unit_cost_usd is used but a note
        is added.

        Disqualified suppliers (non-USD, None cost, etc.) receive 0.
        Returns (score_by_id, note_by_id).
        """
        score_map: dict[str, float] = {}
        note_map:  dict[str, str]   = {}

        # Separate qualified (can price) from disqualified
        priceable = []
        for s in suppliers:
            if self._disqualification_reason(s):
                score_map[s.supplier_id] = 0.0
                note_map[s.supplier_id]  = "Disqualified — no cost score assigned."
            else:
                priceable.append(s)

        if not priceable:
            return score_map, note_map

        # Build comparable costs
        comparable: dict[str, float] = {}
        shipping_unknown_ids: list[str] = []

        for s in priceable:
            base = s.unit_cost_usd  # already validated non-None, > 0, USD

            if s.cost_includes_shipping is True:
                comparable[s.supplier_id] = base  # type: ignore[arg-type]
            elif s.shipping_cost_usd is not None:
                comparable[s.supplier_id] = base + s.shipping_cost_usd  # type: ignore[operator]
            else:
                comparable[s.supplier_id] = base  # type: ignore[arg-type]
                shipping_unknown_ids.append(s.supplier_id)

        if shipping_unknown_ids:
            notes.append(
                "Shipping cost unknown for some suppliers "
                f"({', '.join(shipping_unknown_ids)}). "
                "Cost scores use unit cost only — totals may understate actual cost."
            )

        # Relative scoring: cheapest = 100
        min_cost = min(comparable.values())

        for s in priceable:
            comp_cost = comparable[s.supplier_id]
            cs = round((min_cost / comp_cost) * 100.0, 2) if comp_cost > 0 else 0.0

            # Build a note describing what cost was used
            if s.cost_includes_shipping is True:
                cn = (
                    f"Cost includes shipping (${comp_cost:.2f} all-in). "
                    f"Relative score: {cs:.1f}/100."
                )
            elif s.shipping_cost_usd is not None:
                cn = (
                    f"Unit ${s.unit_cost_usd:.2f} + shipping "
                    f"${s.shipping_cost_usd:.2f} = ${comp_cost:.2f}. "
                    f"Relative score: {cs:.1f}/100."
                )
            else:
                cn = (
                    f"Unit cost ${s.unit_cost_usd:.2f} only "
                    f"(shipping unknown). "
                    f"Relative score: {cs:.1f}/100 — may change when shipping is known."
                )
                if s.minimum_order_quantity > 1:
                    cn += (
                        f" Note: MOQ is {s.minimum_order_quantity} units; "
                        "per-unit cost comparison may not reflect actual order cost."
                    )

            score_map[s.supplier_id] = cs
            note_map[s.supplier_id]  = cn

        return score_map, note_map

    # ------------------------------------------------------------------
    # Disqualification
    # ------------------------------------------------------------------

    @staticmethod
    def _disqualification_reason(s: SupplierResearch) -> str:
        """Return a reason string if the supplier should be disqualified, else ''."""
        if s.unit_cost_usd is None:
            return "unit_cost_usd is None — cannot calculate pricing."
        if s.unit_cost_usd <= 0:
            return f"unit_cost_usd must be > 0, got {s.unit_cost_usd}."
        if s.currency.upper() != "USD":
            return (
                f"Currency is '{s.currency}', not USD. "
                "Cannot pass non-USD costs into the Pricing Engine."
            )
        if s.availability.upper() == "OUT_OF_STOCK":
            return "Supplier is OUT_OF_STOCK."
        return ""

    # ------------------------------------------------------------------
    # Recommendation band
    # ------------------------------------------------------------------

    @staticmethod
    def _recommendation(overall_score: float) -> str:
        if overall_score >= 70.0:
            return "RECOMMENDED"
        if overall_score >= 50.0:
            return "ACCEPTABLE"
        return "RISKY"

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
            raise ValueError("Supplier researcher weights cannot be negative.")
        if abs(sum(self.weights.values()) - 1.0) > 1e-6:
            raise ValueError("Supplier researcher weights must total 1.0.")
