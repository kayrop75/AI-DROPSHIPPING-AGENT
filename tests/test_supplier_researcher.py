"""
Tests for the Supplier model and SupplierResearcher service (Step 4).

Coverage
--------
 1. Supplier model: valid creation, auto-UUID.
 2. Supplier model: negative unit_cost_usd rejected by Pydantic.
 3. Supplier model: platform_rating > 5 rejected.
 4. Supplier model: minimum_order_quantity < 1 rejected.
 5. Supplier model: product_id empty string rejected.
 6. Supplier model: data_verified defaults to False.
 7. SupplierResearcher: default weights accepted.
 8. SupplierResearcher: custom weights accepted.
 9. SupplierResearcher: weights not summing to 1.0 → ValueError.
10. SupplierResearcher: negative weight → ValueError.
11. SupplierResearcher: wrong weight keys → ValueError.
12. Disqualification: unit_cost_usd None → DISQUALIFIED.
13. Disqualification: unit_cost_usd <= 0 → DISQUALIFIED.
14. Disqualification: non-USD currency → DISQUALIFIED.
15. Disqualification: OUT_OF_STOCK → DISQUALIFIED.
16. Disqualification: IN_STOCK with valid cost → not disqualified.
17. INSUFFICIENT DATA: all scoring fields missing (but cost present).
18. Missing fields list names the absent fields.
19. Missing fields list is empty when all data present.
20. Reliability score: full data, manual calculation.
21. Reliability score: missing platform_rating noted.
22. Reliability score: platform_rating out of range → ValueError.
23. Reliability score: negative review_count → ValueError.
24. Reliability score: negative years_active → ValueError.
25. Fulfilment score: tracked shipping present adds 40 pts.
26. Fulfilment score: untracked shipping adds 0, no missing entry.
27. Fulfilment score: unknown tracking → 0 pts + missing entry.
28. Fulfilment score: delivery < 7 days → 40 pts.
29. Fulfilment score: delivery 7–14 days → 25 pts.
30. Fulfilment score: delivery 14–21 days → 10 pts.
31. Fulfilment score: delivery > 21 days → 0 pts.
32. Fulfilment score: negative max_delivery_days → ValueError.
33. Cost score: cheapest supplier scores 100.
34. Cost score: relative scoring across three suppliers.
35. Cost score: shipping bundled uses unit cost directly.
36. Cost score: shipping cost added when available.
37. Cost score: missing shipping cost flagged in note, not disqualified.
38. Cost score: MOQ > 1 noted in cost_score_note.
39. Recommendation: overall >= 70 → RECOMMENDED.
40. Recommendation: overall 50–69 → ACCEPTABLE.
41. Recommendation: overall < 50 → RISKY.
42. rank_suppliers: highest score first.
43. rank_suppliers: disqualified suppliers always last.
44. rank_suppliers: empty list returns empty list.
45. compare: returns all suppliers in ranked_evaluations.
46. compare: recommended_supplier_id is the top qualified supplier.
47. compare: best_unit_cost_usd is set from recommended supplier.
48. compare: empty list returns empty result with a note.
49. compare: single supplier adds a note about no relative comparison.
50. Duplicate supplier_ids: both evaluated independently.
51. Product link: Supplier.product_id matches Product.id.
52. Pricing integration: best_unit_cost_usd feeds calculate_pricing() correctly.
53. Pricing integration: pricing result unaffected by reliability scores.
54. Product status unaffected by supplier research.
55. SupplierEvaluation is a dataclass instance.
56. SupplierComparisonResult is a dataclass instance.
57. All sub-scores exposed alongside overall_score.
58. data_verified=False preserved in SupplierEvaluation.
59. data_verified=True preserved in SupplierEvaluation.
60. No qualified supplier → recommended_supplier_id is None.

Run with:
    pytest tests/test_supplier_researcher.py -v
"""

import math
import pytest

from src.dropship_agent.models.supplier import (
    Supplier,
    SupplierResearch,
    SupplierEvaluation,
    SupplierComparisonResult,
    AvailabilityStatus,
    FulfilmentType,
)
from src.dropship_agent.services.supplier_researcher import SupplierResearcher
from src.dropship_agent.models.product import Product, ProductStatus
from src.dropship_agent.services.pricing import calculate_pricing


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def researcher() -> SupplierResearcher:
    return SupplierResearcher()


@pytest.fixture
def full_supplier() -> SupplierResearch:
    """A SupplierResearch with all scoring fields populated."""
    return SupplierResearch(
        supplier_id="SUP-001",
        unit_cost_usd=8.50,
        currency="USD",
        minimum_order_quantity=1,
        cost_includes_shipping=False,
        availability="IN_STOCK",
        has_tracked_shipping=True,
        min_delivery_days=5,
        max_delivery_days=10,
        shipping_cost_usd=2.00,
        platform_rating=4.5,
        review_count=500,
        years_active=5,
        return_policy_available=True,
        fulfilment_type="DROPSHIP",
        data_verified=True,
    )


@pytest.fixture
def minimal_supplier() -> SupplierResearch:
    """A SupplierResearch with only the required fields to avoid disqualification."""
    return SupplierResearch(
        supplier_id="SUP-MIN",
        unit_cost_usd=10.00,
        currency="USD",
        availability="IN_STOCK",
    )


@pytest.fixture
def lantern_product() -> Product:
    return Product(
        name="Rechargeable LED Lantern",
        category="Home & Outdoors",
        supplier_name="AliExpress Supplier",
        supplier_url="https://aliexpress.com/item/example",
        supplier_cost=8.00,
        shipping_cost=2.00,
        other_costs=0.00,
        selling_price=22.00,
    )


# ---------------------------------------------------------------------------
# 1–6: Supplier model
# ---------------------------------------------------------------------------

def test_supplier_valid_creation():
    s = Supplier(name="Acme Supplies", product_id="prod-123", unit_cost_usd=5.00)
    assert s.id is not None and len(s.id) > 0
    assert s.name == "Acme Supplies"
    assert s.product_id == "prod-123"


def test_supplier_auto_uuid_unique():
    s1 = Supplier(name="A", product_id="p1", unit_cost_usd=5.0)
    s2 = Supplier(name="B", product_id="p1", unit_cost_usd=5.0)
    assert s1.id != s2.id


def test_supplier_negative_unit_cost_rejected():
    with pytest.raises(Exception):
        Supplier(name="Bad", product_id="p1", unit_cost_usd=-1.0)


def test_supplier_platform_rating_above_5_rejected():
    with pytest.raises(Exception):
        Supplier(name="Bad", product_id="p1", unit_cost_usd=5.0, platform_rating=5.1)


def test_supplier_minimum_order_quantity_below_1_rejected():
    with pytest.raises(Exception):
        Supplier(name="Bad", product_id="p1", unit_cost_usd=5.0, minimum_order_quantity=0)


def test_supplier_empty_product_id_rejected():
    with pytest.raises(Exception):
        Supplier(name="Bad", product_id="", unit_cost_usd=5.0)


def test_supplier_data_verified_defaults_false():
    s = Supplier(name="Test", product_id="p1", unit_cost_usd=5.0)
    assert s.data_verified is False


# ---------------------------------------------------------------------------
# 7–11: SupplierResearcher constructor
# ---------------------------------------------------------------------------

def test_default_weights_accepted():
    r = SupplierResearcher()
    assert abs(sum(r.weights.values()) - 1.0) < 1e-6


def test_custom_weights_accepted():
    r = SupplierResearcher(weights={"reliability": 0.6, "fulfilment": 0.3, "cost": 0.1})
    assert r.weights["reliability"] == 0.6


def test_weights_not_summing_to_one_raises():
    with pytest.raises(ValueError, match="must total 1.0"):
        SupplierResearcher(weights={"reliability": 0.5, "fulfilment": 0.5, "cost": 0.5})


def test_negative_weight_raises():
    with pytest.raises(ValueError, match="cannot be negative"):
        SupplierResearcher(weights={"reliability": -0.1, "fulfilment": 0.6, "cost": 0.5})


def test_wrong_weight_keys_raise():
    with pytest.raises(ValueError, match="keys"):
        SupplierResearcher(weights={"demand": 0.5, "trust": 0.3, "speed": 0.2})


# ---------------------------------------------------------------------------
# 12–16: Disqualification
# ---------------------------------------------------------------------------

def test_none_cost_disqualified(researcher):
    s = SupplierResearch(supplier_id="S1", unit_cost_usd=None, availability="IN_STOCK")
    result = researcher.evaluate(s)
    assert result.disqualified is True
    assert result.recommendation == "DISQUALIFIED"
    assert "unit_cost_usd" in result.disqualification_reason


def test_zero_cost_disqualified(researcher):
    s = SupplierResearch(supplier_id="S1", unit_cost_usd=0.0, availability="IN_STOCK")
    result = researcher.evaluate(s)
    assert result.disqualified is True


def test_negative_cost_disqualified(researcher):
    s = SupplierResearch(supplier_id="S1", unit_cost_usd=-5.0, availability="IN_STOCK")
    result = researcher.evaluate(s)
    assert result.disqualified is True


def test_non_usd_currency_disqualified(researcher):
    s = SupplierResearch(supplier_id="S1", unit_cost_usd=8.0, currency="CNY",
                         availability="IN_STOCK")
    result = researcher.evaluate(s)
    assert result.disqualified is True
    assert "USD" in result.disqualification_reason


def test_out_of_stock_disqualified(researcher):
    s = SupplierResearch(supplier_id="S1", unit_cost_usd=8.0, currency="USD",
                         availability="OUT_OF_STOCK")
    result = researcher.evaluate(s)
    assert result.disqualified is True
    assert "OUT_OF_STOCK" in result.disqualification_reason


def test_in_stock_with_valid_cost_not_disqualified(researcher):
    s = SupplierResearch(supplier_id="S1", unit_cost_usd=8.0, currency="USD",
                         availability="IN_STOCK")
    result = researcher.evaluate(s)
    assert result.disqualified is False


# ---------------------------------------------------------------------------
# 17–19: INSUFFICIENT DATA / missing fields
# ---------------------------------------------------------------------------

def test_all_scoring_fields_missing_returns_insufficient_data(researcher):
    """Cost present but all reliability and fulfilment fields None."""
    s = SupplierResearch(supplier_id="S1", unit_cost_usd=10.0, availability="IN_STOCK")
    result = researcher.evaluate(s)
    assert result.recommendation == "INSUFFICIENT DATA"
    assert result.overall_score == 0.0


def test_missing_fields_named_correctly(researcher):
    s = SupplierResearch(
        supplier_id="S1",
        unit_cost_usd=10.0,
        availability="IN_STOCK",
        platform_rating=4.0,   # present
        review_count=None,     # missing
        years_active=None,     # missing
        has_tracked_shipping=True,
        max_delivery_days=10,
        return_policy_available=None,  # missing
    )
    result = researcher.evaluate(s)
    assert "review_count" in result.missing_fields
    assert "years_active" in result.missing_fields
    assert "return_policy_available" in result.missing_fields
    assert "platform_rating" not in result.missing_fields


def test_missing_fields_empty_when_all_present(researcher, full_supplier):
    result = researcher.evaluate(full_supplier)
    assert result.missing_fields == []


# ---------------------------------------------------------------------------
# 20–24: Reliability score
# ---------------------------------------------------------------------------

def test_reliability_score_full_data(researcher):
    """
    platform_rating=4.5 → 4.5/5 × 60 = 54.0
    review_count=500    → log10(501)/4 × 20 = (2.6998/4) × 20 ≈ 13.50
    years_active=5      → 5/10 × 20 = 10.0
    total reliability   ≈ 77.5
    """
    s = SupplierResearch(
        supplier_id="S1",
        unit_cost_usd=10.0,
        availability="IN_STOCK",
        platform_rating=4.5,
        review_count=500,
        years_active=5,
        has_tracked_shipping=True,
        max_delivery_days=10,
        return_policy_available=True,
    )
    result = researcher.evaluate(s)
    expected_rel = (4.5 / 5.0) * 60.0 + (min(math.log10(501) / 4.0, 1.0)) * 20.0 + (5 / 10) * 20.0
    assert abs(result.reliability_score - round(expected_rel, 2)) < 0.01


def test_missing_platform_rating_noted(researcher):
    s = SupplierResearch(
        supplier_id="S1",
        unit_cost_usd=10.0,
        availability="IN_STOCK",
        platform_rating=None,
        review_count=100,
        years_active=3,
        has_tracked_shipping=True,
        max_delivery_days=7,
        return_policy_available=True,
    )
    result = researcher.evaluate(s)
    assert "platform_rating" in result.missing_fields
    # Should not be INSUFFICIENT DATA since other fields are present
    assert result.recommendation != "INSUFFICIENT DATA"


def test_platform_rating_above_5_raises(researcher):
    s = SupplierResearch(supplier_id="S1", unit_cost_usd=10.0, availability="IN_STOCK",
                         platform_rating=5.1, review_count=100, years_active=3,
                         has_tracked_shipping=True, max_delivery_days=10,
                         return_policy_available=True)
    with pytest.raises(ValueError, match="platform_rating"):
        researcher.evaluate(s)


def test_negative_review_count_raises(researcher):
    s = SupplierResearch(supplier_id="S1", unit_cost_usd=10.0, availability="IN_STOCK",
                         platform_rating=4.0, review_count=-1, years_active=3,
                         has_tracked_shipping=True, max_delivery_days=10,
                         return_policy_available=True)
    with pytest.raises(ValueError, match="review_count"):
        researcher.evaluate(s)


def test_negative_years_active_raises(researcher):
    s = SupplierResearch(supplier_id="S1", unit_cost_usd=10.0, availability="IN_STOCK",
                         platform_rating=4.0, review_count=100, years_active=-1,
                         has_tracked_shipping=True, max_delivery_days=10,
                         return_policy_available=True)
    with pytest.raises(ValueError, match="years_active"):
        researcher.evaluate(s)


# ---------------------------------------------------------------------------
# 25–32: Fulfilment score
# ---------------------------------------------------------------------------

def test_tracked_shipping_adds_40_pts(researcher):
    s = SupplierResearch(
        supplier_id="S1", unit_cost_usd=10.0, availability="IN_STOCK",
        platform_rating=4.0, review_count=100, years_active=3,
        has_tracked_shipping=True, max_delivery_days=10,
        return_policy_available=False,
    )
    result = researcher.evaluate(s)
    # fulfilment = 40 (tracked) + 25 (7–14 days) + 0 (no return) = 65
    assert result.fulfilment_score == 65.0


def test_untracked_shipping_adds_0_no_missing(researcher):
    s = SupplierResearch(
        supplier_id="S1", unit_cost_usd=10.0, availability="IN_STOCK",
        platform_rating=4.0, review_count=100, years_active=3,
        has_tracked_shipping=False, max_delivery_days=10,
        return_policy_available=False,
    )
    result = researcher.evaluate(s)
    assert "has_tracked_shipping" not in result.missing_fields
    # fulfilment = 0 (untracked) + 25 (7–14 days) + 0 = 25
    assert result.fulfilment_score == 25.0


def test_unknown_tracking_adds_0_and_missing(researcher):
    s = SupplierResearch(
        supplier_id="S1", unit_cost_usd=10.0, availability="IN_STOCK",
        platform_rating=4.0, review_count=100, years_active=3,
        has_tracked_shipping=None, max_delivery_days=10,
        return_policy_available=False,
    )
    result = researcher.evaluate(s)
    assert "has_tracked_shipping" in result.missing_fields


def test_delivery_under_7_days(researcher):
    s = SupplierResearch(
        supplier_id="S1", unit_cost_usd=10.0, availability="IN_STOCK",
        platform_rating=4.0, review_count=100, years_active=3,
        has_tracked_shipping=True, max_delivery_days=6,
        return_policy_available=True,
    )
    result = researcher.evaluate(s)
    # fulfilment = 40 + 40 + 20 = 100
    assert result.fulfilment_score == 100.0


def test_delivery_7_to_14_days(researcher):
    s = SupplierResearch(
        supplier_id="S1", unit_cost_usd=10.0, availability="IN_STOCK",
        platform_rating=4.0, review_count=100, years_active=3,
        has_tracked_shipping=False, max_delivery_days=14,
        return_policy_available=False,
    )
    result = researcher.evaluate(s)
    # 0 + 25 + 0 = 25
    assert result.fulfilment_score == 25.0


def test_delivery_14_to_21_days(researcher):
    s = SupplierResearch(
        supplier_id="S1", unit_cost_usd=10.0, availability="IN_STOCK",
        platform_rating=4.0, review_count=100, years_active=3,
        has_tracked_shipping=False, max_delivery_days=21,
        return_policy_available=False,
    )
    result = researcher.evaluate(s)
    # 0 + 10 + 0 = 10
    assert result.fulfilment_score == 10.0


def test_delivery_over_21_days(researcher):
    s = SupplierResearch(
        supplier_id="S1", unit_cost_usd=10.0, availability="IN_STOCK",
        platform_rating=4.0, review_count=100, years_active=3,
        has_tracked_shipping=False, max_delivery_days=30,
        return_policy_available=False,
    )
    result = researcher.evaluate(s)
    # 0 + 0 + 0 = 0
    assert result.fulfilment_score == 0.0


def test_negative_max_delivery_days_raises(researcher):
    s = SupplierResearch(
        supplier_id="S1", unit_cost_usd=10.0, availability="IN_STOCK",
        platform_rating=4.0, review_count=100, years_active=3,
        has_tracked_shipping=True, max_delivery_days=-1,
        return_policy_available=True,
    )
    with pytest.raises(ValueError, match="max_delivery_days"):
        researcher.evaluate(s)


# ---------------------------------------------------------------------------
# 33–38: Cost scoring
# ---------------------------------------------------------------------------

def test_cheapest_supplier_scores_100(researcher):
    cheap     = SupplierResearch(supplier_id="CHEAP", unit_cost_usd=5.0,
                                  availability="IN_STOCK",
                                  shipping_cost_usd=1.0)
    expensive = SupplierResearch(supplier_id="EXP",   unit_cost_usd=10.0,
                                  availability="IN_STOCK",
                                  shipping_cost_usd=1.0)
    result = researcher.compare([cheap, expensive], product_id="P1")
    cheap_eval = next(e for e in result.ranked_evaluations if e.supplier_id == "CHEAP")
    assert cheap_eval.cost_score == 100.0


def test_relative_cost_scoring_three_suppliers(researcher):
    """
    Supplier A: unit $5 + ship $1 = $6  → 6/6 × 100 = 100
    Supplier B: unit $8 + ship $2 = $10 → 6/10 × 100 = 60
    Supplier C: unit $12            = $12 (ship unknown) → 6/12 × 100 = 50
    """
    a = SupplierResearch(supplier_id="A", unit_cost_usd=5.0,
                          availability="IN_STOCK", shipping_cost_usd=1.0)
    b = SupplierResearch(supplier_id="B", unit_cost_usd=8.0,
                          availability="IN_STOCK", shipping_cost_usd=2.0)
    c = SupplierResearch(supplier_id="C", unit_cost_usd=12.0,
                          availability="IN_STOCK")
    result = researcher.compare([a, b, c], product_id="P1")
    evals = {e.supplier_id: e for e in result.ranked_evaluations}
    assert evals["A"].cost_score == 100.0
    assert evals["B"].cost_score == 60.0
    assert evals["C"].cost_score == 50.0


def test_bundled_shipping_uses_unit_cost(researcher):
    s = SupplierResearch(
        supplier_id="S1", unit_cost_usd=12.0, availability="IN_STOCK",
        cost_includes_shipping=True,
    )
    result = researcher.compare([s], product_id="P1")
    evalu = result.ranked_evaluations[0]
    assert "all-in" in evalu.cost_score_note.lower() or "includes shipping" in evalu.cost_score_note.lower()


def test_shipping_cost_added_when_available(researcher):
    s = SupplierResearch(
        supplier_id="S1", unit_cost_usd=8.0, availability="IN_STOCK",
        shipping_cost_usd=2.0,
    )
    result = researcher.compare([s], product_id="P1")
    evalu = result.ranked_evaluations[0]
    assert "10.00" in evalu.cost_score_note  # 8 + 2 = 10


def test_missing_shipping_cost_flagged_in_note(researcher):
    s = SupplierResearch(
        supplier_id="S1", unit_cost_usd=8.0, availability="IN_STOCK",
        shipping_cost_usd=None,
    )
    result = researcher.compare([s], product_id="P1")
    evalu = result.ranked_evaluations[0]
    assert "shipping unknown" in evalu.cost_score_note.lower() or \
           "shipping cost" in " ".join(result.comparison_notes).lower()


def test_moq_above_1_noted_in_cost_note(researcher):
    s = SupplierResearch(
        supplier_id="S1", unit_cost_usd=8.0, availability="IN_STOCK",
        minimum_order_quantity=10,
    )
    result = researcher.compare([s], product_id="P1")
    evalu = result.ranked_evaluations[0]
    assert "MOQ" in evalu.cost_score_note or "moq" in evalu.cost_score_note.lower()


# ---------------------------------------------------------------------------
# 39–41: Recommendation bands
# ---------------------------------------------------------------------------

def test_overall_70_or_above_is_recommended():
    """
    With weights reliability=1.0, fulfilment=0.0, cost=0.0:
      platform_rating=5.0 → 60.0 pts
      review_count=1000   → log10(1001)/4 × 20 ≈ 15.0 pts
      years_active=10     → 10/10 × 20 = 20.0 pts
      reliability total   ≈ 95+ → overall ≥ 70 → RECOMMENDED
    """
    r = SupplierResearcher(weights={"reliability": 1.0, "fulfilment": 0.0, "cost": 0.0})
    s = SupplierResearch(
        supplier_id="S1", unit_cost_usd=10.0, availability="IN_STOCK",
        platform_rating=5.0, review_count=1000, years_active=10,
        has_tracked_shipping=False, max_delivery_days=25,
        return_policy_available=False,
    )
    result = r.evaluate(s)
    assert result.overall_score >= 70.0
    assert result.recommendation == "RECOMMENDED"


def test_overall_50_to_69_is_acceptable():
    """
    With weights reliability=1.0, fulfilment=0.0, cost=0.0:
      platform_rating=4.0 → 48.0 pts
      review_count=10     → log10(11)/4 × 20 ≈ 5.2 pts
      years_active=0      → 0 pts
      reliability total   ≈ 53.2 → overall in [50, 70) → ACCEPTABLE
    """
    r = SupplierResearcher(weights={"reliability": 1.0, "fulfilment": 0.0, "cost": 0.0})
    s = SupplierResearch(
        supplier_id="S1", unit_cost_usd=10.0, availability="IN_STOCK",
        platform_rating=4.0, review_count=10, years_active=0,
        has_tracked_shipping=False, max_delivery_days=25,
        return_policy_available=False,
    )
    result = r.evaluate(s)
    assert 50.0 <= result.overall_score < 70.0
    assert result.recommendation == "ACCEPTABLE"


def test_overall_below_50_is_risky():
    """
    With weights reliability=1.0, fulfilment=0.0, cost=0.0:
      platform_rating=2.0 → 24.0 pts
      review_count=0      → 0 pts
      years_active=0      → 0 pts
      reliability total   = 24.0 → overall < 50 → RISKY
    """
    r = SupplierResearcher(weights={"reliability": 1.0, "fulfilment": 0.0, "cost": 0.0})
    s = SupplierResearch(
        supplier_id="S1", unit_cost_usd=10.0, availability="IN_STOCK",
        platform_rating=2.0, review_count=0, years_active=0,
        has_tracked_shipping=False, max_delivery_days=25,
        return_policy_available=False,
    )
    result = r.evaluate(s)
    assert result.overall_score < 50.0
    assert result.recommendation == "RISKY"


# ---------------------------------------------------------------------------
# 42–44: rank_suppliers
# ---------------------------------------------------------------------------

def test_rank_suppliers_highest_first(researcher):
    high = SupplierResearch(supplier_id="H", unit_cost_usd=5.0,
                             availability="IN_STOCK",
                             platform_rating=5.0, review_count=1000,
                             years_active=10, has_tracked_shipping=True,
                             max_delivery_days=5, return_policy_available=True)
    low  = SupplierResearch(supplier_id="L", unit_cost_usd=15.0,
                             availability="IN_STOCK",
                             platform_rating=2.0, review_count=10,
                             years_active=1, has_tracked_shipping=False,
                             max_delivery_days=28, return_policy_available=False)
    ranked = researcher.rank_suppliers([low, high])
    assert ranked[0].supplier_id == "H"
    assert ranked[1].supplier_id == "L"


def test_disqualified_always_last(researcher):
    good = SupplierResearch(supplier_id="G", unit_cost_usd=10.0,
                             availability="IN_STOCK",
                             platform_rating=4.0, review_count=200,
                             years_active=4, has_tracked_shipping=True,
                             max_delivery_days=10, return_policy_available=True)
    bad  = SupplierResearch(supplier_id="B", unit_cost_usd=None,
                             availability="IN_STOCK")
    ranked = researcher.rank_suppliers([bad, good])
    assert ranked[-1].supplier_id == "B"
    assert ranked[-1].disqualified is True


def test_rank_suppliers_empty_list(researcher):
    assert researcher.rank_suppliers([]) == []


# ---------------------------------------------------------------------------
# 45–49: compare()
# ---------------------------------------------------------------------------

def test_compare_returns_all_suppliers(researcher):
    sups = [
        SupplierResearch(supplier_id=f"S{i}", unit_cost_usd=float(5 + i),
                          availability="IN_STOCK")
        for i in range(4)
    ]
    result = researcher.compare(sups, product_id="P1")
    assert len(result.ranked_evaluations) == 4


def test_compare_recommended_is_top_qualified(researcher):
    good = SupplierResearch(supplier_id="GOOD", unit_cost_usd=8.0,
                             availability="IN_STOCK",
                             platform_rating=4.5, review_count=500,
                             years_active=5, has_tracked_shipping=True,
                             max_delivery_days=7, return_policy_available=True)
    poor = SupplierResearch(supplier_id="POOR", unit_cost_usd=15.0,
                             availability="IN_STOCK",
                             platform_rating=2.0, review_count=5,
                             years_active=1, has_tracked_shipping=False,
                             max_delivery_days=30, return_policy_available=False)
    result = researcher.compare([poor, good], product_id="P1")
    assert result.recommended_supplier_id == "GOOD"


def test_compare_best_unit_cost_set(researcher):
    s = SupplierResearch(supplier_id="S1", unit_cost_usd=9.99,
                          availability="IN_STOCK",
                          platform_rating=4.0, review_count=100,
                          years_active=3, has_tracked_shipping=True,
                          max_delivery_days=10, return_policy_available=True)
    result = researcher.compare([s], product_id="P1")
    assert result.best_unit_cost_usd == 9.99


def test_compare_empty_list_returns_note(researcher):
    result = researcher.compare([], product_id="P1")
    assert result.ranked_evaluations == []
    assert result.recommended_supplier_id is None
    assert len(result.comparison_notes) > 0


def test_compare_single_supplier_adds_note(researcher):
    s = SupplierResearch(supplier_id="S1", unit_cost_usd=10.0,
                          availability="IN_STOCK")
    result = researcher.compare([s], product_id="P1")
    combined = " ".join(result.comparison_notes).lower()
    assert "one supplier" in combined or "single" in combined


# ---------------------------------------------------------------------------
# 50: Duplicate supplier_ids
# ---------------------------------------------------------------------------

def test_duplicate_supplier_ids_evaluated_independently(researcher):
    """Two SupplierResearch objects sharing the same supplier_id are both evaluated."""
    s1 = SupplierResearch(supplier_id="SAME", unit_cost_usd=8.0,
                           availability="IN_STOCK",
                           platform_rating=4.5, review_count=500,
                           years_active=5, has_tracked_shipping=True,
                           max_delivery_days=7, return_policy_available=True)
    s2 = SupplierResearch(supplier_id="SAME", unit_cost_usd=12.0,
                           availability="IN_STOCK",
                           platform_rating=3.0, review_count=50,
                           years_active=2, has_tracked_shipping=False,
                           max_delivery_days=20, return_policy_available=False)
    result = researcher.compare([s1, s2], product_id="P1")
    assert len(result.ranked_evaluations) == 2


# ---------------------------------------------------------------------------
# 51: Product link
# ---------------------------------------------------------------------------

def test_supplier_product_id_matches_product(lantern_product):
    s = Supplier(
        name="Test Supplier",
        platform="AliExpress",
        product_id=lantern_product.id,
        unit_cost_usd=8.00,
    )
    assert s.product_id == lantern_product.id


# ---------------------------------------------------------------------------
# 52–53: Pricing Engine integration
# ---------------------------------------------------------------------------

def test_best_cost_feeds_pricing_engine(researcher, lantern_product):
    """
    best_unit_cost_usd from SupplierComparisonResult passes directly
    into calculate_pricing() without error.
    """
    s = SupplierResearch(supplier_id="S1", unit_cost_usd=8.50,
                          availability="IN_STOCK",
                          platform_rating=4.0, review_count=200,
                          years_active=3, has_tracked_shipping=True,
                          max_delivery_days=10, return_policy_available=True)
    result = researcher.compare([s], product_id=lantern_product.id)

    assert result.best_unit_cost_usd is not None
    pricing = calculate_pricing(
        supplier_cost=result.best_unit_cost_usd,
        shipping_cost=2.00,
        other_costs=0.00,
        selling_price=lantern_product.selling_price,
    )
    assert pricing.total_landed_cost == round(result.best_unit_cost_usd + 2.00, 2)
    assert pricing.is_viable is True


def test_pricing_unaffected_by_reliability_scores(researcher, lantern_product):
    """Supplier reliability scores do not alter the Product's pricing fields."""
    lantern_product.supplier_cost = 8.00
    assert lantern_product.total_cost == 10.00
    assert lantern_product.gross_profit == 12.00
    assert lantern_product.gross_margin_pct == 54.55

    # Evaluate a supplier — the Product must be unchanged afterwards
    s = SupplierResearch(supplier_id="S1", unit_cost_usd=8.00,
                          availability="IN_STOCK",
                          platform_rating=4.0, review_count=200,
                          years_active=3, has_tracked_shipping=True,
                          max_delivery_days=10, return_policy_available=True)
    researcher.evaluate(s)

    assert lantern_product.total_cost == 10.00
    assert lantern_product.gross_profit == 12.00
    assert lantern_product.gross_margin_pct == 54.55


# ---------------------------------------------------------------------------
# 54: Product status
# ---------------------------------------------------------------------------

def test_product_status_unaffected_by_supplier_research(researcher, lantern_product):
    s = SupplierResearch(supplier_id="S1", unit_cost_usd=8.00,
                          availability="IN_STOCK")
    researcher.evaluate(s)
    assert lantern_product.status == ProductStatus.DISCOVERED
    lantern_product.status = ProductStatus.RESEARCHING
    assert lantern_product.status == ProductStatus.RESEARCHING


# ---------------------------------------------------------------------------
# 55–57: Return types and sub-score exposure
# ---------------------------------------------------------------------------

def test_supplier_evaluation_is_dataclass(researcher, full_supplier):
    result = researcher.evaluate(full_supplier)
    assert isinstance(result, SupplierEvaluation)


def test_supplier_comparison_result_is_dataclass(researcher, full_supplier):
    result = researcher.compare([full_supplier], product_id="P1")
    assert isinstance(result, SupplierComparisonResult)


def test_all_subscores_exposed(researcher, full_supplier):
    result = researcher.evaluate(full_supplier)
    assert hasattr(result, "reliability_score")
    assert hasattr(result, "fulfilment_score")
    assert hasattr(result, "cost_score")
    assert hasattr(result, "overall_score")
    assert result.reliability_score >= 0
    assert result.fulfilment_score >= 0
    assert result.overall_score >= 0


# ---------------------------------------------------------------------------
# 58–59: data_verified flag
# ---------------------------------------------------------------------------

def test_data_verified_false_preserved(researcher):
    s = SupplierResearch(supplier_id="S1", unit_cost_usd=10.0,
                          availability="IN_STOCK", data_verified=False)
    result = researcher.evaluate(s)
    assert result.data_verified is False


def test_data_verified_true_preserved(researcher, full_supplier):
    full_supplier.data_verified = True
    result = researcher.evaluate(full_supplier)
    assert result.data_verified is True


# ---------------------------------------------------------------------------
# 60: No qualified supplier
# ---------------------------------------------------------------------------

def test_no_qualified_supplier_recommended_id_is_none(researcher):
    """All suppliers disqualified → recommended_supplier_id is None."""
    s1 = SupplierResearch(supplier_id="S1", unit_cost_usd=None, availability="IN_STOCK")
    s2 = SupplierResearch(supplier_id="S2", unit_cost_usd=5.0, availability="OUT_OF_STOCK")
    result = researcher.compare([s1, s2], product_id="P1")
    assert result.recommended_supplier_id is None
    assert result.best_unit_cost_usd is None
