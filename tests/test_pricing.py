"""
Tests for the pricing service.

What we are testing
-------------------
The pricing service is a pure function: same inputs always produce the
same outputs. No database, no network, no randomness. That makes it
very easy to test exhaustively.

We test:
1. The correct numbers for the Step 2 example product.
2. Viability flag behaves correctly (positive vs negative profit).
3. High-margin and zero-margin edge cases.
4. Every invalid input raises a ValueError with a helpful message.

Run with:
    pytest tests/test_pricing.py -v
"""

import pytest
from src.dropship_agent.services.pricing import calculate_pricing, PricingResult


# ---------------------------------------------------------------------------
# 1. The Step 2 reference numbers
#
# These are the numbers we committed to in the design document.
# If a future change breaks these, the project's core math is wrong.
# ---------------------------------------------------------------------------

def test_step2_total_landed_cost():
    """
    supplier $8 + shipping $2 + other $0 = $10 total landed cost.
    "Landed cost" means the full cost of getting the product to the customer.
    """
    result = calculate_pricing(
        supplier_cost=8.00,
        shipping_cost=2.00,
        other_costs=0.00,
        selling_price=22.00,
    )
    assert result.total_landed_cost == 10.00


def test_step2_gross_profit():
    """
    selling price ($22) - landed cost ($10) = $12 gross profit.
    This is the money we keep before operating expenses.
    """
    result = calculate_pricing(
        supplier_cost=8.00,
        shipping_cost=2.00,
        other_costs=0.00,
        selling_price=22.00,
    )
    assert result.gross_profit == 12.00


def test_step2_gross_margin_pct():
    """
    ($12 / $22) * 100 = 54.55%.
    More than half of every sale covers costs and profit — a healthy margin.
    """
    result = calculate_pricing(
        supplier_cost=8.00,
        shipping_cost=2.00,
        other_costs=0.00,
        selling_price=22.00,
    )
    assert result.gross_margin_pct == 54.55


def test_step2_product_is_viable():
    result = calculate_pricing(
        supplier_cost=8.00,
        shipping_cost=2.00,
        other_costs=0.00,
        selling_price=22.00,
    )
    assert result.is_viable is True


# ---------------------------------------------------------------------------
# 2. The return type is a PricingResult
# ---------------------------------------------------------------------------

def test_returns_pricing_result_instance():
    """
    The function should always return a PricingResult, not a dict or tuple.
    This keeps the calling code clean and type-safe.
    """
    result = calculate_pricing(10.0, 2.0, 0.0, 25.0)
    assert isinstance(result, PricingResult)


def test_pricing_result_is_immutable():
    """
    PricingResult is a frozen dataclass.
    Once created, no code should be able to alter the numbers.
    """
    result = calculate_pricing(10.0, 2.0, 0.0, 25.0)
    with pytest.raises(Exception):
        result.gross_profit = 999.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 3. Viability flag
# ---------------------------------------------------------------------------

def test_loss_making_product_is_not_viable():
    """
    If we spend more than we earn, gross_profit is negative
    and is_viable is False. We should know this before listing anything.
    """
    result = calculate_pricing(
        supplier_cost=20.00,
        shipping_cost=5.00,
        other_costs=0.00,
        selling_price=15.00,
    )
    assert result.gross_profit == -10.00
    assert result.is_viable is False


def test_break_even_product_is_not_viable():
    """
    Zero profit means we work for free. is_viable requires strictly positive
    gross profit — breaking even is not acceptable.
    """
    result = calculate_pricing(
        supplier_cost=10.00,
        shipping_cost=0.00,
        other_costs=0.00,
        selling_price=10.00,
    )
    assert result.gross_profit == 0.00
    assert result.is_viable is False


# ---------------------------------------------------------------------------
# 4. All three cost components are included
# ---------------------------------------------------------------------------

def test_other_costs_reduce_profit():
    """
    Packaging, payment fees, and platform fees are real costs.
    Forgetting them is one of the most common dropshipping mistakes.
    This test ensures other_costs is never silently ignored.
    """
    without_fees = calculate_pricing(8.0, 2.0, 0.0, 22.0)
    with_fees    = calculate_pricing(8.0, 2.0, 1.50, 22.0)

    assert with_fees.total_landed_cost == 11.50
    assert with_fees.gross_profit      == 10.50
    assert with_fees.gross_profit < without_fees.gross_profit


# ---------------------------------------------------------------------------
# 5. High-margin product
# ---------------------------------------------------------------------------

def test_high_margin_product():
    """
    A product with very low cost and high selling price.
    Gross margin should approach (but never reach) 100%.
    """
    result = calculate_pricing(
        supplier_cost=1.00,
        shipping_cost=0.00,
        other_costs=0.00,
        selling_price=100.00,
    )
    assert result.total_landed_cost == 1.00
    assert result.gross_profit      == 99.00
    assert result.gross_margin_pct  == 99.00
    assert result.is_viable is True


# ---------------------------------------------------------------------------
# 6. Invalid inputs must raise ValueError
# ---------------------------------------------------------------------------

def test_negative_supplier_cost_raises():
    """
    A negative supplier cost is a data entry error.
    The function must catch it immediately rather than returning garbage.
    """
    with pytest.raises(ValueError, match="supplier_cost"):
        calculate_pricing(-1.0, 0.0, 0.0, 10.0)


def test_negative_shipping_cost_raises():
    with pytest.raises(ValueError, match="shipping_cost"):
        calculate_pricing(5.0, -0.50, 0.0, 10.0)


def test_negative_other_costs_raises():
    with pytest.raises(ValueError, match="other_costs"):
        calculate_pricing(5.0, 0.0, -1.0, 10.0)


def test_negative_selling_price_raises():
    with pytest.raises(ValueError, match="selling_price"):
        calculate_pricing(5.0, 0.0, 0.0, -10.0)


def test_zero_selling_price_raises():
    """
    A selling price of zero makes gross margin undefined (division by zero).
    We raise a clear error rather than returning NaN or infinity.
    """
    with pytest.raises(ValueError, match="selling_price is 0"):
        calculate_pricing(5.0, 0.0, 0.0, 0.0)
