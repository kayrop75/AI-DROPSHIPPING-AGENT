"""
Tests for the Product data model.

Run with:  pytest tests/test_product_model.py -v
"""

import pytest
from src.dropship_agent.models.product import Product, ProductStatus


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def lantern() -> Product:
    """The example product from Step 2 — fictional research data."""
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
# Identity
# ---------------------------------------------------------------------------

def test_product_gets_an_id(lantern):
    assert lantern.id is not None
    assert len(lantern.id) > 0


def test_two_products_have_different_ids():
    p1 = Product(name="A", supplier_cost=5.0, selling_price=10.0)
    p2 = Product(name="B", supplier_cost=5.0, selling_price=10.0)
    assert p1.id != p2.id


# ---------------------------------------------------------------------------
# Default state
# ---------------------------------------------------------------------------

def test_new_product_status_is_discovered(lantern):
    assert lantern.status == ProductStatus.DISCOVERED


def test_scores_are_none_when_not_evaluated(lantern):
    assert lantern.demand_score is None
    assert lantern.competition_score is None


# ---------------------------------------------------------------------------
# Profit calculations — the numbers from Step 2
# ---------------------------------------------------------------------------

def test_total_cost(lantern):
    # supplier $8 + shipping $2 + other $0 = $10
    assert lantern.total_cost == 10.00


def test_gross_profit(lantern):
    # selling $22 - total cost $10 = $12
    assert lantern.gross_profit == 12.00


def test_gross_margin_pct(lantern):
    # ($12 / $22) * 100 = 54.55%
    assert lantern.gross_margin_pct == 54.55


def test_is_profitable(lantern):
    assert lantern.is_profitable is True


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_zero_selling_price_does_not_crash():
    p = Product(name="Freebie", supplier_cost=5.0, selling_price=0.0)
    assert p.gross_margin_pct == 0.0
    assert p.is_profitable is False


def test_loss_making_product():
    p = Product(name="Bad deal", supplier_cost=20.0, selling_price=15.0)
    assert p.gross_profit == -5.00
    assert p.is_profitable is False


def test_other_costs_included_in_total():
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
# Validation — Pydantic should reject bad data
# ---------------------------------------------------------------------------

def test_negative_supplier_cost_is_rejected():
    with pytest.raises(Exception):
        Product(name="Bad", supplier_cost=-1.0, selling_price=10.0)


def test_demand_score_out_of_range_is_rejected():
    with pytest.raises(Exception):
        Product(name="Bad", supplier_cost=5.0, selling_price=10.0, demand_score=101.0)


def test_status_transition():
    p = Product(name="Test", supplier_cost=5.0, selling_price=15.0)
    assert p.status == ProductStatus.DISCOVERED
    p.status = ProductStatus.UNDER_REVIEW
    assert p.status == ProductStatus.UNDER_REVIEW
