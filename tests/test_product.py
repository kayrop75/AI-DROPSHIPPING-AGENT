"""
Tests for the Product data model.

What we are testing
-------------------
1. Every new product gets a unique ID automatically.
2. A new product always starts with status DISCOVERED.
3. Scores start as None — the agent hasn't evaluated anything yet.
4. The computed fields (total_cost, gross_profit, gross_margin_pct,
   is_profitable) return the correct numbers.
5. Pydantic rejects invalid data: negative costs, scores out of range.
6. Status can move forward through the workflow.

Run with:
    pytest tests/test_product.py -v
"""

import pytest
from src.dropship_agent.models.product import Product, ProductStatus


# ---------------------------------------------------------------------------
# Shared test product
#
# A "fixture" in pytest is a reusable setup function.
# Any test that declares `lantern` as a parameter receives a fresh copy.
# ---------------------------------------------------------------------------

@pytest.fixture
def lantern() -> Product:
    """
    The example product from Step 2.
    supplier $8 + shipping $2 + other $0, selling at $22.
    """
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
# 1. Identity
# ---------------------------------------------------------------------------

def test_product_gets_an_id_automatically(lantern):
    """
    We never want to create a product without an ID.
    Pydantic generates a UUID automatically via default_factory.
    """
    assert lantern.id is not None
    assert len(lantern.id) > 0


def test_two_products_always_have_different_ids():
    """
    UUIDs are random — the chance of a collision is astronomically low.
    If this test ever fails, our ID generation is broken.
    """
    p1 = Product(name="A", supplier_cost=5.0, selling_price=10.0)
    p2 = Product(name="B", supplier_cost=5.0, selling_price=10.0)
    assert p1.id != p2.id


# ---------------------------------------------------------------------------
# 2. Default workflow state
# ---------------------------------------------------------------------------

def test_new_product_starts_as_discovered(lantern):
    """
    Every product enters the pipeline at DISCOVERED.
    It shouldn't jump straight to APPROVED — a human reviews it first.
    """
    assert lantern.status == ProductStatus.DISCOVERED


# ---------------------------------------------------------------------------
# 3. Scores start unevaluated
# ---------------------------------------------------------------------------

def test_demand_score_is_none_before_research(lantern):
    """
    None explicitly means "not evaluated yet".
    We refuse to invent a score when we have no evidence.
    """
    assert lantern.demand_score is None


def test_competition_score_is_none_before_research(lantern):
    assert lantern.competition_score is None


# ---------------------------------------------------------------------------
# 4. Profit calculations — the numbers from Step 2
# ---------------------------------------------------------------------------

def test_total_cost_is_sum_of_all_costs(lantern):
    """
    Total cost = supplier ($8) + shipping ($2) + other ($0) = $10.
    """
    assert lantern.total_cost == 10.00


def test_gross_profit_is_revenue_minus_cost(lantern):
    """
    Gross profit = selling price ($22) - total cost ($10) = $12.
    """
    assert lantern.gross_profit == 12.00


def test_gross_margin_pct_is_correct(lantern):
    """
    Gross margin = (gross profit / selling price) * 100
                 = ($12 / $22) * 100
                 = 54.55%

    This tells us 54.55 cents of every dollar sold stays with us
    before operating expenses.
    """
    assert lantern.gross_margin_pct == 54.55


def test_profitable_product_is_flagged(lantern):
    assert lantern.is_profitable is True


def test_other_costs_are_included_in_total():
    """
    Packaging and platform fees must be part of the landed cost.
    Missing them inflates our apparent profit.
    """
    p = Product(
        name="With fees",
        supplier_cost=8.0,
        shipping_cost=2.0,
        other_costs=1.50,
        selling_price=22.0,
    )
    assert p.total_cost == 11.50
    assert p.gross_profit == 10.50


# ---------------------------------------------------------------------------
# 5. Edge cases
# ---------------------------------------------------------------------------

def test_loss_making_product_has_negative_profit():
    """
    If costs exceed the selling price, gross profit is negative.
    The model should represent this accurately, not clamp to zero.
    """
    p = Product(name="Bad deal", supplier_cost=20.0, selling_price=15.0)
    assert p.gross_profit == -5.00
    assert p.is_profitable is False


def test_zero_selling_price_returns_zero_margin():
    """
    A selling price of zero makes margin undefined mathematically.
    We return 0.0 rather than crashing with a division-by-zero error.
    """
    p = Product(name="Freebie", supplier_cost=5.0, selling_price=0.0)
    assert p.gross_margin_pct == 0.0
    assert p.is_profitable is False


# ---------------------------------------------------------------------------
# 6. Validation — Pydantic must reject bad data
# ---------------------------------------------------------------------------

def test_negative_supplier_cost_is_rejected():
    """
    A negative supplier cost is a data entry error.
    Pydantic's ge=0.0 constraint should raise a ValidationError.
    """
    with pytest.raises(Exception):
        Product(name="Bad", supplier_cost=-1.0, selling_price=10.0)


def test_demand_score_above_100_is_rejected():
    """
    Scores are capped at 100. Anything higher is meaningless.
    """
    with pytest.raises(Exception):
        Product(name="Bad", supplier_cost=5.0, selling_price=10.0, demand_score=101.0)


def test_demand_score_below_0_is_rejected():
    with pytest.raises(Exception):
        Product(name="Bad", supplier_cost=5.0, selling_price=10.0, demand_score=-1.0)


# ---------------------------------------------------------------------------
# 7. Status transitions
# ---------------------------------------------------------------------------

def test_status_can_move_through_workflow():
    """
    A product must be able to advance from DISCOVERED all the way to APPROVED.
    We test each transition to make sure no status value is accidentally broken.
    """
    p = Product(name="Test", supplier_cost=5.0, selling_price=15.0)

    assert p.status == ProductStatus.DISCOVERED

    p.status = ProductStatus.RESEARCHING
    assert p.status == ProductStatus.RESEARCHING

    p.status = ProductStatus.UNDER_REVIEW
    assert p.status == ProductStatus.UNDER_REVIEW

    p.status = ProductStatus.APPROVED
    assert p.status == ProductStatus.APPROVED


def test_product_can_be_rejected():
    p = Product(name="Reject me", supplier_cost=5.0, selling_price=15.0)
    p.status = ProductStatus.REJECTED
    assert p.status == ProductStatus.REJECTED
