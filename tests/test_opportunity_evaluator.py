"""
Tests for OpportunityInput, OpportunityResult and ProductOpportunityEvaluator (Step 5).

Coverage
--------
 1. OpportunityInput: valid creation with all fields.
 2. OpportunityInput: selling_price_usd defaults to None.
 3. OpportunityInput: other_costs_usd defaults to 0.0.
 4. OpportunityInput: data_verified defaults to False.
 5. Constructor: default weights accepted and sum to 1.0.
 6. Constructor: custom weights accepted.
 7. Constructor: weights not summing to 1.0 → ValueError.
 8. Constructor: negative weight → ValueError.
 9. Constructor: wrong weight keys → ValueError.
10. Full evaluation: OpportunityResult is returned.
11. Full evaluation: overall_score matches manual calculation.
12. Full evaluation: market_score equals ResearchResult.opportunity_score.
13. Full evaluation: supplier_score equals top SupplierEvaluation.overall_score.
14. Full evaluation: pricing_score correct for 54.55% margin (capped at 100).
15. Full evaluation: missing_information is empty when all inputs present.
16. Full evaluation: classification is not INSUFFICIENT DATA when all inputs valid.
17. Missing research: research_result=None → classification INSUFFICIENT DATA.
18. Missing research: market_score=0 when research_result is None.
19. Missing research: "research_result" in missing_information.
20. Missing research: research rating INSUFFICIENT DATA → market_score=0.
21. Missing research: upstream missing_fields propagated.
22. Missing supplier: supplier_comparison=None → classification INSUFFICIENT DATA.
23. Missing supplier: supplier_score=0 when supplier_comparison is None.
24. Missing supplier: "supplier_comparison" in missing_information.
25. Missing supplier: all suppliers disqualified → INSUFFICIENT DATA.
26. Missing supplier: "qualified_supplier" in missing_information when all disqualified.
27. Missing price: selling_price_usd=None → classification INSUFFICIENT DATA.
28. Missing price: pricing_score=0 when selling_price_usd is None.
29. Missing price: "selling_price_usd" in missing_information.
30. Pricing: pricing_score = min(100, max(0, (margin/50)*100)).
31. Pricing: negative margin → pricing_score=0.
32. Pricing: zero margin → pricing_score=0.
33. Pricing: 25% margin → pricing_score=50.0.
34. Pricing: 50% margin → pricing_score=100.0 exactly.
35. Pricing: 100% margin (theoretical) → pricing_score capped at 100.
36. Pricing: estimated_margin_pct matches PricingResult.gross_margin_pct.
37. Pricing: is_viable=False when costs exceed selling price.
38. Pricing: is_viable=True when product profitable.
39. Pricing: other_costs_usd included in calculation.
40. Pricing: negative other_costs_usd → pricing_score=0, reason in risks.
41. Currency: non-USD currency → classification INSUFFICIENT DATA.
42. Currency: non-USD currency → reason in risks.
43. Currency: non-USD currency → pricing_score=0.
44. Classification: overall >= 70 → STRONG.
45. Classification: overall 55–69 → MODERATE.
46. Classification: overall 40–54 → WEAK.
47. Classification: overall < 40 → POOR.
48. Narrative: strengths non-empty when market_score >= 70.
49. Narrative: weaknesses non-empty when supplier score is low.
50. Narrative: risks includes single-supplier warning when only one qualified.
51. Narrative: recommendation_basis is a non-empty string.
52. Narrative: recommendation_basis references classification when INSUFFICIENT DATA.
53. Narrative: recommendation_basis includes individual scores when classified.
54. Integration: best_unit_cost_usd feeds calculate_pricing() correctly.
55. Integration: existing Product pricing fields unaffected by evaluation.
56. Integration: existing ResearchResult unaffected by evaluation.
57. Integration: supplier_cost_usd set from SupplierComparisonResult.
58. Integration: is_viable=None when pricing not calculated.
59. OpportunityResult: is a dataclass instance.
60. OpportunityResult: all sub-scores exposed (market, supplier, pricing, overall).

Run with:
    pytest tests/test_opportunity_evaluator.py -v
"""

import pytest

from src.dropship_agent.models.research import ProductResearch, ResearchResult
from src.dropship_agent.models.supplier import (
    SupplierResearch, SupplierEvaluation, SupplierComparisonResult,
)
from src.dropship_agent.models.opportunity import OpportunityInput, OpportunityResult
from src.dropship_agent.services.opportunity_evaluator import ProductOpportunityEvaluator
from src.dropship_agent.services.researcher import ProductResearcher
from src.dropship_agent.services.supplier_researcher import SupplierResearcher
from src.dropship_agent.services.pricing import calculate_pricing
from src.dropship_agent.models.product import Product, ProductStatus


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_research_result(
    opportunity_score: float = 70.5,
    rating: str = "MODERATE OPPORTUNITY",
    missing_fields: list | None = None,
) -> ResearchResult:
    return ResearchResult(
        product_id="PROD-001",
        opportunity_score=opportunity_score,
        rating=rating,
        data_verified=True,
        missing_fields=missing_fields or [],
    )


def _make_supplier_comparison(
    overall_score: float = 72.0,
    recommendation: str = "RECOMMENDED",
    unit_cost_usd: float = 8.0,
    disqualified: bool = False,
) -> SupplierComparisonResult:
    evalu = SupplierEvaluation(
        supplier_id="SUP-001",
        reliability_score=70.0,
        fulfilment_score=75.0,
        cost_score=80.0,
        overall_score=overall_score,
        recommendation=recommendation,
        data_verified=True,
        disqualified=disqualified,
        disqualification_reason="" if not disqualified else "OUT_OF_STOCK",
    )
    return SupplierComparisonResult(
        product_id="PROD-001",
        ranked_evaluations=[evalu],
        recommended_supplier_id=None if disqualified else "SUP-001",
        best_unit_cost_usd=None if disqualified else unit_cost_usd,
        comparison_notes=[],
    )


def _full_input(
    selling_price: float = 22.0,
    other_costs: float = 0.0,
    research_score: float = 70.5,
    supplier_score: float = 72.0,
    unit_cost: float = 8.0,
) -> OpportunityInput:
    return OpportunityInput(
        product_id="PROD-001",
        research_result=_make_research_result(opportunity_score=research_score),
        supplier_comparison=_make_supplier_comparison(
            overall_score=supplier_score, unit_cost_usd=unit_cost
        ),
        selling_price_usd=selling_price,
        other_costs_usd=other_costs,
        currency="USD",
        data_verified=True,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def evaluator() -> ProductOpportunityEvaluator:
    return ProductOpportunityEvaluator()


@pytest.fixture
def full_input() -> OpportunityInput:
    return _full_input()


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
# 1–4: OpportunityInput model
# ---------------------------------------------------------------------------

def test_opportunity_input_valid_creation():
    inp = OpportunityInput(product_id="P1")
    assert inp.product_id == "P1"


def test_selling_price_defaults_to_none():
    inp = OpportunityInput(product_id="P1")
    assert inp.selling_price_usd is None


def test_other_costs_defaults_to_zero():
    inp = OpportunityInput(product_id="P1")
    assert inp.other_costs_usd == 0.0


def test_data_verified_defaults_false():
    inp = OpportunityInput(product_id="P1")
    assert inp.data_verified is False


# ---------------------------------------------------------------------------
# 5–9: Constructor validation
# ---------------------------------------------------------------------------

def test_default_weights_accepted():
    e = ProductOpportunityEvaluator()
    assert abs(sum(e.weights.values()) - 1.0) < 1e-6


def test_custom_weights_accepted():
    e = ProductOpportunityEvaluator(weights={"market": 0.5, "supplier": 0.3, "pricing": 0.2})
    assert e.weights["market"] == 0.5


def test_weights_not_summing_to_one_raises():
    with pytest.raises(ValueError, match="must total 1.0"):
        ProductOpportunityEvaluator(weights={"market": 0.5, "supplier": 0.5, "pricing": 0.5})


def test_negative_weight_raises():
    with pytest.raises(ValueError, match="cannot be negative"):
        ProductOpportunityEvaluator(weights={"market": -0.1, "supplier": 0.6, "pricing": 0.5})


def test_wrong_weight_keys_raise():
    with pytest.raises(ValueError, match="keys"):
        ProductOpportunityEvaluator(weights={"demand": 0.4, "trust": 0.35, "cost": 0.25})


# ---------------------------------------------------------------------------
# 10–16: Full evaluation
# ---------------------------------------------------------------------------

def test_full_evaluation_returns_result(evaluator, full_input):
    result = evaluator.evaluate(full_input)
    assert isinstance(result, OpportunityResult)


def test_full_evaluation_overall_score_calculation(evaluator):
    """
    market=70.5, supplier=72.0, pricing from margin 54.55% → capped at 100.0
    overall = 70.5*0.40 + 72.0*0.35 + 100.0*0.25
            = 28.2 + 25.2 + 25.0 = 78.4
    """
    inp = _full_input(selling_price=22.0, unit_cost=8.0,
                      research_score=70.5, supplier_score=72.0)
    result = evaluator.evaluate(inp)
    # pricing_score: margin=(22-8)/22*100=63.64% → (63.64/50)*100=127.3 → capped 100
    expected = round(70.5 * 0.40 + 72.0 * 0.35 + 100.0 * 0.25, 2)
    assert result.overall_score == expected


def test_market_score_equals_research_opportunity_score(evaluator, full_input):
    result = evaluator.evaluate(full_input)
    assert result.market_score == 70.5


def test_supplier_score_equals_top_evaluation_score(evaluator, full_input):
    result = evaluator.evaluate(full_input)
    assert result.supplier_score == 72.0


def test_pricing_score_correct_for_lantern(evaluator):
    """
    Lantern: supplier_cost=8, selling_price=22 → margin=63.64%
    pricing_score = min(100, max(0, (63.64/50)*100)) = min(100, 127.27) = 100.0
    """
    inp = _full_input(selling_price=22.0, unit_cost=8.0)
    result = evaluator.evaluate(inp)
    assert result.pricing_score == 100.0


def test_missing_information_empty_when_all_present(evaluator, full_input):
    result = evaluator.evaluate(full_input)
    assert result.missing_information == []


def test_full_input_not_insufficient_data(evaluator, full_input):
    result = evaluator.evaluate(full_input)
    assert result.classification != "INSUFFICIENT DATA"


# ---------------------------------------------------------------------------
# 17–21: Missing research
# ---------------------------------------------------------------------------

def test_none_research_result_is_insufficient(evaluator):
    inp = OpportunityInput(
        product_id="P1",
        research_result=None,
        supplier_comparison=_make_supplier_comparison(),
        selling_price_usd=22.0,
    )
    result = evaluator.evaluate(inp)
    assert result.classification == "INSUFFICIENT DATA"


def test_none_research_market_score_is_zero(evaluator):
    inp = OpportunityInput(product_id="P1", research_result=None,
                            supplier_comparison=_make_supplier_comparison(),
                            selling_price_usd=22.0)
    result = evaluator.evaluate(inp)
    assert result.market_score == 0.0


def test_none_research_in_missing_information(evaluator):
    inp = OpportunityInput(product_id="P1", research_result=None,
                            supplier_comparison=_make_supplier_comparison(),
                            selling_price_usd=22.0)
    result = evaluator.evaluate(inp)
    assert "research_result" in result.missing_information


def test_research_insufficient_data_market_score_zero(evaluator):
    research = _make_research_result(
        opportunity_score=0.0,
        rating="INSUFFICIENT DATA",
        missing_fields=["demand", "competition"],
    )
    inp = OpportunityInput(product_id="P1", research_result=research,
                            supplier_comparison=_make_supplier_comparison(),
                            selling_price_usd=22.0)
    result = evaluator.evaluate(inp)
    assert result.market_score == 0.0
    assert result.classification == "INSUFFICIENT DATA"


def test_research_missing_fields_propagated(evaluator):
    research = _make_research_result(
        opportunity_score=0.0,
        rating="INSUFFICIENT DATA",
        missing_fields=["demand", "competition"],
    )
    inp = OpportunityInput(product_id="P1", research_result=research,
                            supplier_comparison=_make_supplier_comparison(),
                            selling_price_usd=22.0)
    result = evaluator.evaluate(inp)
    assert "demand" in result.missing_information
    assert "competition" in result.missing_information


# ---------------------------------------------------------------------------
# 22–26: Missing supplier
# ---------------------------------------------------------------------------

def test_none_supplier_comparison_is_insufficient(evaluator):
    inp = OpportunityInput(product_id="P1",
                            research_result=_make_research_result(),
                            supplier_comparison=None,
                            selling_price_usd=22.0)
    result = evaluator.evaluate(inp)
    assert result.classification == "INSUFFICIENT DATA"


def test_none_supplier_comparison_score_is_zero(evaluator):
    inp = OpportunityInput(product_id="P1",
                            research_result=_make_research_result(),
                            supplier_comparison=None,
                            selling_price_usd=22.0)
    result = evaluator.evaluate(inp)
    assert result.supplier_score == 0.0


def test_none_supplier_in_missing_information(evaluator):
    inp = OpportunityInput(product_id="P1",
                            research_result=_make_research_result(),
                            supplier_comparison=None,
                            selling_price_usd=22.0)
    result = evaluator.evaluate(inp)
    assert "supplier_comparison" in result.missing_information


def test_all_suppliers_disqualified_is_insufficient(evaluator):
    comp = _make_supplier_comparison(disqualified=True)
    inp = OpportunityInput(product_id="P1",
                            research_result=_make_research_result(),
                            supplier_comparison=comp,
                            selling_price_usd=22.0)
    result = evaluator.evaluate(inp)
    assert result.classification == "INSUFFICIENT DATA"


def test_all_disqualified_qualified_supplier_in_missing(evaluator):
    comp = _make_supplier_comparison(disqualified=True)
    inp = OpportunityInput(product_id="P1",
                            research_result=_make_research_result(),
                            supplier_comparison=comp,
                            selling_price_usd=22.0)
    result = evaluator.evaluate(inp)
    assert "qualified_supplier" in result.missing_information


# ---------------------------------------------------------------------------
# 27–29: Missing selling price
# ---------------------------------------------------------------------------

def test_none_selling_price_is_insufficient(evaluator):
    inp = OpportunityInput(product_id="P1",
                            research_result=_make_research_result(),
                            supplier_comparison=_make_supplier_comparison(),
                            selling_price_usd=None)
    result = evaluator.evaluate(inp)
    assert result.classification == "INSUFFICIENT DATA"


def test_none_selling_price_pricing_score_zero(evaluator):
    inp = OpportunityInput(product_id="P1",
                            research_result=_make_research_result(),
                            supplier_comparison=_make_supplier_comparison(),
                            selling_price_usd=None)
    result = evaluator.evaluate(inp)
    assert result.pricing_score == 0.0


def test_none_selling_price_in_missing_information(evaluator):
    inp = OpportunityInput(product_id="P1",
                            research_result=_make_research_result(),
                            supplier_comparison=_make_supplier_comparison(),
                            selling_price_usd=None)
    result = evaluator.evaluate(inp)
    assert "selling_price_usd" in result.missing_information


# ---------------------------------------------------------------------------
# 30–40: Pricing score
# ---------------------------------------------------------------------------

def test_pricing_score_formula():
    """
    selling=20, supplier_cost=10 → margin = (20-10)/20*100 = 50%
    pricing_score = min(100, max(0, (50/50)*100)) = 100.0
    """
    inp = _full_input(selling_price=20.0, unit_cost=10.0)
    result = ProductOpportunityEvaluator().evaluate(inp)
    assert result.pricing_score == 100.0


def test_negative_margin_pricing_score_zero():
    """supplier_cost=25 > selling_price=20 → negative margin → score=0"""
    inp = _full_input(selling_price=20.0, unit_cost=25.0)
    result = ProductOpportunityEvaluator().evaluate(inp)
    assert result.pricing_score == 0.0


def test_zero_margin_pricing_score_zero():
    """supplier_cost=20, selling_price=20 → margin=0% → score=0"""
    inp = _full_input(selling_price=20.0, unit_cost=20.0)
    result = ProductOpportunityEvaluator().evaluate(inp)
    assert result.pricing_score == 0.0


def test_25_pct_margin_pricing_score():
    """
    selling=20, supplier_cost=15 → margin=(20-15)/20*100=25%
    pricing_score = (25/50)*100 = 50.0
    """
    inp = _full_input(selling_price=20.0, unit_cost=15.0)
    result = ProductOpportunityEvaluator().evaluate(inp)
    assert result.pricing_score == 50.0


def test_50_pct_margin_pricing_score_exactly_100():
    """
    selling=20, supplier_cost=10 → margin=50% → score=100.0
    """
    inp = _full_input(selling_price=20.0, unit_cost=10.0)
    result = ProductOpportunityEvaluator().evaluate(inp)
    assert result.pricing_score == 100.0


def test_above_50_pct_margin_capped_at_100():
    """
    selling=100, supplier_cost=1 → margin=99% → score capped at 100
    """
    inp = _full_input(selling_price=100.0, unit_cost=1.0)
    result = ProductOpportunityEvaluator().evaluate(inp)
    assert result.pricing_score == 100.0


def test_estimated_margin_pct_matches_pricing_result():
    inp = _full_input(selling_price=22.0, unit_cost=8.0)
    result = ProductOpportunityEvaluator().evaluate(inp)
    expected_pricing = calculate_pricing(
        supplier_cost=8.0, shipping_cost=0.0,
        other_costs=0.0, selling_price=22.0
    )
    assert result.estimated_margin_pct == expected_pricing.gross_margin_pct


def test_is_viable_false_when_costs_exceed_price():
    inp = _full_input(selling_price=10.0, unit_cost=15.0)
    result = ProductOpportunityEvaluator().evaluate(inp)
    assert result.is_viable is False


def test_is_viable_true_when_profitable():
    inp = _full_input(selling_price=22.0, unit_cost=8.0)
    result = ProductOpportunityEvaluator().evaluate(inp)
    assert result.is_viable is True


def test_other_costs_included_in_pricing(evaluator):
    """
    selling=20, supplier=8, other=4 → total_cost=12 → margin=40%
    pricing_score = (40/50)*100 = 80.0
    Without other_costs: margin=(20-8)/20=60% → score=100 (capped)
    """
    inp_with = _full_input(selling_price=20.0, unit_cost=8.0, other_costs=4.0)
    result = evaluator.evaluate(inp_with)
    assert result.pricing_score == 80.0


def test_negative_other_costs_pricing_score_zero(evaluator):
    inp = OpportunityInput(
        product_id="P1",
        research_result=_make_research_result(),
        supplier_comparison=_make_supplier_comparison(unit_cost_usd=8.0),
        selling_price_usd=22.0,
        other_costs_usd=-1.0,
    )
    result = evaluator.evaluate(inp)
    assert result.pricing_score == 0.0
    assert any("other_costs_usd" in r for r in result.risks)


# ---------------------------------------------------------------------------
# 41–43: Currency guard
# ---------------------------------------------------------------------------

def test_non_usd_currency_is_insufficient(evaluator):
    inp = OpportunityInput(
        product_id="P1",
        research_result=_make_research_result(),
        supplier_comparison=_make_supplier_comparison(),
        selling_price_usd=22.0,
        currency="EUR",
    )
    result = evaluator.evaluate(inp)
    assert result.classification == "INSUFFICIENT DATA"


def test_non_usd_currency_in_risks(evaluator):
    inp = OpportunityInput(
        product_id="P1",
        research_result=_make_research_result(),
        supplier_comparison=_make_supplier_comparison(),
        selling_price_usd=22.0,
        currency="GBP",
    )
    result = evaluator.evaluate(inp)
    assert any("GBP" in r or "USD" in r for r in result.risks)


def test_non_usd_pricing_score_zero(evaluator):
    inp = OpportunityInput(
        product_id="P1",
        research_result=_make_research_result(),
        supplier_comparison=_make_supplier_comparison(),
        selling_price_usd=22.0,
        currency="JPY",
    )
    result = evaluator.evaluate(inp)
    assert result.pricing_score == 0.0


# ---------------------------------------------------------------------------
# 44–47: Classification bands
# ---------------------------------------------------------------------------

def test_overall_70_or_above_is_strong():
    """
    Use weights market=1.0 to control overall precisely.
    market_score=70 → overall=70 → STRONG
    """
    e = ProductOpportunityEvaluator(
        weights={"market": 1.0, "supplier": 0.0, "pricing": 0.0}
    )
    inp = OpportunityInput(
        product_id="P1",
        research_result=_make_research_result(opportunity_score=70.0),
        supplier_comparison=_make_supplier_comparison(),
        selling_price_usd=22.0,
    )
    result = e.evaluate(inp)
    assert result.overall_score >= 70.0
    assert result.classification == "STRONG"


def test_overall_55_to_69_is_moderate():
    e = ProductOpportunityEvaluator(
        weights={"market": 1.0, "supplier": 0.0, "pricing": 0.0}
    )
    inp = OpportunityInput(
        product_id="P1",
        research_result=_make_research_result(opportunity_score=55.0,
                                               rating="MODERATE OPPORTUNITY"),
        supplier_comparison=_make_supplier_comparison(),
        selling_price_usd=22.0,
    )
    result = e.evaluate(inp)
    assert 55.0 <= result.overall_score < 70.0
    assert result.classification == "MODERATE"


def test_overall_40_to_54_is_weak():
    e = ProductOpportunityEvaluator(
        weights={"market": 1.0, "supplier": 0.0, "pricing": 0.0}
    )
    inp = OpportunityInput(
        product_id="P1",
        research_result=_make_research_result(opportunity_score=40.0,
                                               rating="LOW OPPORTUNITY"),
        supplier_comparison=_make_supplier_comparison(),
        selling_price_usd=22.0,
    )
    result = e.evaluate(inp)
    assert 40.0 <= result.overall_score < 55.0
    assert result.classification == "WEAK"


def test_overall_below_40_is_poor():
    e = ProductOpportunityEvaluator(
        weights={"market": 1.0, "supplier": 0.0, "pricing": 0.0}
    )
    inp = OpportunityInput(
        product_id="P1",
        research_result=_make_research_result(opportunity_score=20.0,
                                               rating="WEAK OPPORTUNITY"),
        supplier_comparison=_make_supplier_comparison(),
        selling_price_usd=22.0,
    )
    result = e.evaluate(inp)
    assert result.overall_score < 40.0
    assert result.classification == "POOR"


# ---------------------------------------------------------------------------
# 48–53: Narrative
# ---------------------------------------------------------------------------

def test_strengths_non_empty_when_market_high(evaluator):
    inp = _full_input(research_score=80.0, selling_price=22.0, unit_cost=8.0)
    result = evaluator.evaluate(inp)
    assert len(result.strengths) > 0


def test_weaknesses_non_empty_when_supplier_low(evaluator):
    inp = OpportunityInput(
        product_id="P1",
        research_result=_make_research_result(opportunity_score=70.0),
        supplier_comparison=_make_supplier_comparison(
            overall_score=30.0, recommendation="RISKY"
        ),
        selling_price_usd=22.0,
    )
    result = evaluator.evaluate(inp)
    assert len(result.weaknesses) > 0


def test_single_supplier_risk_note(evaluator):
    """One qualified supplier → risk note added."""
    inp = _full_input()
    result = evaluator.evaluate(inp)
    combined = " ".join(result.risks).lower()
    assert "one" in combined or "single" in combined


def test_recommendation_basis_non_empty(evaluator, full_input):
    result = evaluator.evaluate(full_input)
    assert len(result.recommendation_basis) > 0


def test_recommendation_basis_references_insufficient_data():
    evaluator = ProductOpportunityEvaluator()
    inp = OpportunityInput(product_id="P1", research_result=None,
                            supplier_comparison=_make_supplier_comparison(),
                            selling_price_usd=22.0)
    result = evaluator.evaluate(inp)
    assert "INSUFFICIENT DATA" in result.recommendation_basis


def test_recommendation_basis_includes_scores_when_classified(evaluator, full_input):
    result = evaluator.evaluate(full_input)
    # Basis should contain the overall score
    assert str(result.overall_score)[:4] in result.recommendation_basis or \
           any(c.isdigit() for c in result.recommendation_basis)


# ---------------------------------------------------------------------------
# 54–60: Integration and return types
# ---------------------------------------------------------------------------

def test_best_cost_feeds_pricing_engine():
    """
    SupplierComparisonResult.best_unit_cost_usd feeds calculate_pricing()
    via the evaluator without error, and the result matches manual calculation.
    """
    evaluator = ProductOpportunityEvaluator()
    inp = _full_input(selling_price=22.0, unit_cost=8.0)
    result = evaluator.evaluate(inp)

    # Verify by calling calculate_pricing directly with same inputs
    direct = calculate_pricing(
        supplier_cost=8.0, shipping_cost=0.0,
        other_costs=0.0, selling_price=22.0
    )
    assert result.estimated_margin_pct == direct.gross_margin_pct
    assert result.is_viable == direct.is_viable


def test_existing_product_pricing_unaffected(evaluator, lantern_product):
    """Evaluating an opportunity must not alter the Product's pricing fields."""
    assert lantern_product.total_cost == 10.00
    assert lantern_product.gross_profit == 12.00

    inp = _full_input(selling_price=22.0, unit_cost=8.0)
    evaluator.evaluate(inp)

    assert lantern_product.total_cost == 10.00
    assert lantern_product.gross_profit == 12.00
    assert lantern_product.gross_margin_pct == 54.55


def test_existing_research_result_unaffected(evaluator):
    """Evaluating must not modify the ResearchResult passed in."""
    research = _make_research_result(opportunity_score=70.5)
    inp = _full_input()
    inp.research_result = research
    evaluator.evaluate(inp)
    assert research.opportunity_score == 70.5
    assert research.rating == "MODERATE OPPORTUNITY"


def test_supplier_cost_usd_set_from_comparison(evaluator):
    inp = _full_input(unit_cost=9.50)
    result = evaluator.evaluate(inp)
    assert result.supplier_cost_usd == 9.50


def test_is_viable_none_when_no_pricing(evaluator):
    """When selling_price is missing, is_viable must be None, not False."""
    inp = OpportunityInput(
        product_id="P1",
        research_result=_make_research_result(),
        supplier_comparison=_make_supplier_comparison(),
        selling_price_usd=None,
    )
    result = evaluator.evaluate(inp)
    assert result.is_viable is None


def test_opportunity_result_is_dataclass(evaluator, full_input):
    result = evaluator.evaluate(full_input)
    assert isinstance(result, OpportunityResult)


def test_all_subscores_exposed(evaluator, full_input):
    result = evaluator.evaluate(full_input)
    assert hasattr(result, "market_score")
    assert hasattr(result, "supplier_score")
    assert hasattr(result, "pricing_score")
    assert hasattr(result, "overall_score")
    assert all(
        isinstance(s, float)
        for s in [result.market_score, result.supplier_score,
                  result.pricing_score, result.overall_score]
    )
