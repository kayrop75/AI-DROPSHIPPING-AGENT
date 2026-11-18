"""
Pricing service.

This module contains one job: given cost inputs, calculate the numbers that
tell us whether a product is worth selling.

It is kept separate from the Product model deliberately.
The model owns the data shape. This service owns the business logic.
That way we can change the pricing rules without touching the data model,
and test both independently.

All amounts are in USD.
"""

from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PricingResult:
    """
    The output of a pricing calculation. Immutable — no one can alter the
    result after it has been produced.

    Attributes
    ----------
    total_landed_cost : float
        Every dollar we spend before making a sale.
        (supplier cost + shipping cost + other costs)

    gross_profit : float
        What we keep after covering landed costs.
        (selling price - total landed cost)
        Can be negative — that means we lose money on each sale.

    gross_margin_pct : float
        Gross profit expressed as a percentage of the selling price.
        A margin of 50 % means half the sale price is profit before
        operating expenses.

    is_viable : bool
        Quick sanity flag. True only when gross profit is strictly positive.
        This is NOT a full go/no-go decision — advertising, payment fees,
        refunds and taxes are not included here.
    """
    total_landed_cost: float
    gross_profit: float
    gross_margin_pct: float
    is_viable: bool


# ---------------------------------------------------------------------------
# Core function
# ---------------------------------------------------------------------------

def calculate_pricing(
    supplier_cost: float,
    shipping_cost: float,
    other_costs: float,
    selling_price: float,
) -> PricingResult:
    """
    Calculate landed cost, gross profit and gross margin for a product.

    Parameters
    ----------
    supplier_cost  : what the supplier charges per unit (USD, >= 0)
    shipping_cost  : delivery cost to the customer (USD, >= 0)
    other_costs    : packaging, platform fees, etc. (USD, >= 0)
    selling_price  : our intended sale price (USD, >= 0)

    Returns
    -------
    PricingResult with all computed fields.

    Raises
    ------
    ValueError  if any input is negative, or if selling_price is zero
                (a zero price makes margin undefined and is almost certainly
                a data entry mistake).
    """

    # --- Input validation ---
    if supplier_cost < 0:
        raise ValueError(f"supplier_cost must be >= 0, got {supplier_cost}")
    if shipping_cost < 0:
        raise ValueError(f"shipping_cost must be >= 0, got {shipping_cost}")
    if other_costs < 0:
        raise ValueError(f"other_costs must be >= 0, got {other_costs}")
    if selling_price < 0:
        raise ValueError(f"selling_price must be >= 0, got {selling_price}")
    if selling_price == 0:
        raise ValueError(
            "selling_price is 0. Set a selling price before calculating margins. "
            "If you intentionally want a free product, handle it outside this function."
        )

    # --- Calculation ---
    total_landed_cost = round(supplier_cost + shipping_cost + other_costs, 2)
    gross_profit      = round(selling_price - total_landed_cost, 2)
    gross_margin_pct  = round((gross_profit / selling_price) * 100, 2)
    is_viable         = gross_profit > 0

    return PricingResult(
        total_landed_cost=total_landed_cost,
        gross_profit=gross_profit,
        gross_margin_pct=gross_margin_pct,
        is_viable=is_viable,
    )
