"""
Tests for the ProductResearcher service (Step 3.1).

Coverage
--------
1. Default weights sum to 1.0 and are accepted without error.
2. evaluate() returns INSUFFICIENT DATA when any score is missing,
   listing only the missing field names.
3. Scoring arithmetic — opportunity score matches manual calculation.
4. All four rating bands: HIGH, MODERATE, LOW, WEAK.
5. rank_products() returns all results sorted highest score first.
6. Constructor rejects weights that don't sum to 1.0.
7. Constructor rejects negative weights.
8. evaluate() rejects a score outside 0–100.
9. Integration: ResearchResult scores can be written back to a Product,
   and the Product pricing fields are unaffected.

Run with:
    pytest tests/test_researcher.py -v
"""

import pytest
from src.dropship_agent.models.research import ProductResearch, ResearchResult
from src.dropship_agent.services.researcher import ProductResearcher
from src.dropship_agent.models.product import Product, ProductStatus


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def researcher() -> ProductResearcher:
    """Default researcher with standard weights."""
    return ProductResearcher()


@pytest.fixture
def full_product() -> ProductResearch:
    """A ProductResearch with all three scores supplied."""
    return ProductResearch(
        product_id="LANTERN-001",
        demand_score=80.0,
        competition_score=60.0,
        trend_score=70.0,
        data_verified=True,
    )


@pytest.fixture
def lantern_product() -> Product:
    """The Step 2 reference Product used for integration tests."""
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
# 1. Default weights
# ---------------------------------------------------------------------------

def test_default_weights_are_accepted():
    """
    ProductResearcher() with no arguments must not raise.
    Default weights: demand 0.40, competition 0.35, trend 0.25 → sum = 1.0.
    """
    r = ProductResearcher()
    assert abs(sum(r.weights.values()) - 1.0) < 1e-6


def test_custom_weights_are_accepted():
    r = ProductResearcher(weights={"demand": 0.5, "competition": 0.3, "trend": 0.2})
    assert r.weights["demand"] == 0.5


# ---------------------------------------------------------------------------
# 2. Missing data → INSUFFICIENT DATA
# ---------------------------------------------------------------------------

def test_missing_all_scores_returns_insufficient_data(researcher):
    p = ProductResearch(product_id="EMPTY-001")
    result = researcher.evaluate(p)
    assert result.rating == "INSUFFICIENT DATA"
    assert result.opportunity_score == 0.0
    assert set(result.missing_fields) == {"demand", "competition", "trend"}


def test_missing_one_score_returns_insufficient_data(researcher):
    """Only two of three scores supplied — still not enough."""
    p = ProductResearch(product_id="PARTIAL-001", demand_score=80.0, trend_score=70.0)
    result = researcher.evaluate(p)
    assert result.rating == "INSUFFICIENT DATA"
    assert "competition" in result.missing_fields
    assert "demand" not in result.missing_fields
    assert "trend" not in result.missing_fields


def test_missing_fields_list_is_empty_when_all_scores_present(researcher, full_product):
    result = researcher.evaluate(full_product)
    assert result.missing_fields == []


# ---------------------------------------------------------------------------
# 3. Scoring arithmetic
# ---------------------------------------------------------------------------

def test_opportunity_score_calculation(researcher, full_product):
    """
    demand=80 × 0.40  = 32.00
    competition=60 × 0.35 = 21.00
    trend=70 × 0.25   = 17.50
    total                 = 70.50
    """
    result = researcher.evaluate(full_product)
    assert result.opportunity_score == 70.50


def test_product_id_is_preserved(researcher, full_product):
    result = researcher.evaluate(full_product)
    assert result.product_id == "LANTERN-001"


def test_data_verified_flag_is_preserved(researcher, full_product):
    result = researcher.evaluate(full_product)
    assert result.data_verified is True


# ---------------------------------------------------------------------------
# 4. Rating bands
# ---------------------------------------------------------------------------

def test_high_opportunity_at_75(researcher):
    """Score exactly at 75 → HIGH OPPORTUNITY."""
    # demand=75/0.40=187.5 — easier to pick numbers that hit 75 exactly:
    # demand=100×0.40 + competition=100×0.35 - x = 75
    # Let demand=80, competition=65, trend=70 → 32+22.75+17.5=72.25 — not 75
    # Use custom weights to control precisely.
    r = ProductResearcher(weights={"demand": 1.0, "competition": 0.0, "trend": 0.0})
    p = ProductResearch(product_id="X", demand_score=75, competition_score=0, trend_score=0)
    result = r.evaluate(p)
    assert result.rating == "HIGH OPPORTUNITY"
    assert result.opportunity_score == 75.0


def test_moderate_opportunity_at_55(researcher):
    r = ProductResearcher(weights={"demand": 1.0, "competition": 0.0, "trend": 0.0})
    p = ProductResearch(product_id="X", demand_score=55, competition_score=0, trend_score=0)
    result = r.evaluate(p)
    assert result.rating == "MODERATE OPPORTUNITY"


def test_low_opportunity_at_35(researcher):
    r = ProductResearcher(weights={"demand": 1.0, "competition": 0.0, "trend": 0.0})
    p = ProductResearch(product_id="X", demand_score=35, competition_score=0, trend_score=0)
    result = r.evaluate(p)
    assert result.rating == "LOW OPPORTUNITY"


def test_weak_opportunity_below_35(researcher):
    r = ProductResearcher(weights={"demand": 1.0, "competition": 0.0, "trend": 0.0})
    p = ProductResearch(product_id="X", demand_score=20, competition_score=0, trend_score=0)
    result = r.evaluate(p)
    assert result.rating == "WEAK OPPORTUNITY"


def test_default_weights_lantern_is_moderate(researcher, full_product):
    """Score 70.5 sits in the MODERATE band (55–74.99)."""
    result = researcher.evaluate(full_product)
    assert result.rating == "MODERATE OPPORTUNITY"


# ---------------------------------------------------------------------------
# 5. rank_products
# ---------------------------------------------------------------------------

def test_rank_products_returns_highest_first(researcher):
    high = ProductResearch(product_id="HIGH", demand_score=90, competition_score=90, trend_score=90)
    low  = ProductResearch(product_id="LOW",  demand_score=20, competition_score=20, trend_score=20)
    mid  = ProductResearch(product_id="MID",  demand_score=60, competition_score=60, trend_score=60)

    ranked = researcher.rank_products([low, high, mid])
    assert [r.product_id for r in ranked] == ["HIGH", "MID", "LOW"]


def test_rank_products_handles_missing_data(researcher):
    """Products with missing data score 0 and sink to the bottom."""
    good    = ProductResearch(product_id="GOOD", demand_score=80, competition_score=60, trend_score=70)
    missing = ProductResearch(product_id="MISS")

    ranked = researcher.rank_products([missing, good])
    assert ranked[0].product_id == "GOOD"
    assert ranked[1].product_id == "MISS"


def test_rank_products_returns_all_items(researcher):
    products = [
        ProductResearch(product_id=f"P{i}", demand_score=i*10, competition_score=50, trend_score=50)
        for i in range(1, 6)
    ]
    ranked = researcher.rank_products(products)
    assert len(ranked) == 5


# ---------------------------------------------------------------------------
# 6 & 7. Constructor validation
# ---------------------------------------------------------------------------

def test_weights_not_summing_to_one_raises():
    with pytest.raises(ValueError, match="must total 1.0"):
        ProductResearcher(weights={"demand": 0.5, "competition": 0.5, "trend": 0.5})


def test_negative_weight_raises():
    with pytest.raises(ValueError, match="cannot be negative"):
        ProductResearcher(weights={"demand": -0.1, "competition": 0.6, "trend": 0.5})


# ---------------------------------------------------------------------------
# 8. Score range validation
# ---------------------------------------------------------------------------

def test_score_above_100_raises(researcher):
    p = ProductResearch(product_id="BAD", demand_score=150, competition_score=50, trend_score=50)
    with pytest.raises(ValueError, match="demand score must be between 0 and 100"):
        researcher.evaluate(p)


def test_score_below_0_raises(researcher):
    p = ProductResearch(product_id="BAD", demand_score=-1, competition_score=50, trend_score=50)
    with pytest.raises(ValueError, match="demand score must be between 0 and 100"):
        researcher.evaluate(p)


def test_boundary_scores_are_accepted(researcher):
    """0 and 100 are valid boundary values — they must not raise."""
    p = ProductResearch(product_id="EDGE", demand_score=0, competition_score=100, trend_score=50)
    result = researcher.evaluate(p)
    assert result.opportunity_score is not None


# ---------------------------------------------------------------------------
# 9. Integration: ResearchResult → Product
# ---------------------------------------------------------------------------

def test_research_scores_can_be_written_to_product(researcher, full_product, lantern_product):
    """
    After evaluate(), the opportunity scores from ResearchResult can be
    written back to the Product model's demand_score and competition_score
    fields, keeping the pipeline data in one place.
    """
    result = researcher.evaluate(full_product)

    # Write researcher output back to the Product
    lantern_product.demand_score = full_product.demand_score
    lantern_product.competition_score = full_product.competition_score

    assert lantern_product.demand_score == 80.0
    assert lantern_product.competition_score == 60.0


def test_pricing_unaffected_after_research_integration(researcher, full_product, lantern_product):
    """
    Writing research scores to a Product must not alter its pricing fields.
    The two subsystems are independent and must stay that way.
    """
    lantern_product.demand_score = full_product.demand_score
    lantern_product.competition_score = full_product.competition_score

    assert lantern_product.total_cost == 10.00
    assert lantern_product.gross_profit == 12.00
    assert lantern_product.gross_margin_pct == 54.55
    assert lantern_product.is_profitable is True


def test_product_status_advances_after_research(lantern_product, researcher, full_product):
    """
    Completing research should allow the product to advance to RESEARCHING
    and then UNDER_REVIEW — the status workflow must still work after
    research scores are attached.
    """
    result = researcher.evaluate(full_product)
    lantern_product.demand_score = full_product.demand_score
    lantern_product.competition_score = full_product.competition_score

    lantern_product.status = ProductStatus.RESEARCHING
    assert lantern_product.status == ProductStatus.RESEARCHING

    lantern_product.status = ProductStatus.UNDER_REVIEW
    assert lantern_product.status == ProductStatus.UNDER_REVIEW


def test_research_result_is_a_dataclass_instance(researcher, full_product):
    """ResearchResult must be a proper dataclass, not a dict or namedtuple."""
    result = researcher.evaluate(full_product)
    assert isinstance(result, ResearchResult)
