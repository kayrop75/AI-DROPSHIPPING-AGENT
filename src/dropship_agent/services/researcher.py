from ..models.research import ProductResearch, ResearchResult


class ProductResearcher:
    """Evaluates dropshipping product opportunities from research data."""

    DEFAULT_WEIGHTS = {
        "demand": 0.40,
        "competition": 0.35,
        "trend": 0.25,
    }

    def __init__(self, weights: dict | None = None):
        self.weights = weights or dict(self.DEFAULT_WEIGHTS)

        if abs(sum(self.weights.values()) - 1.0) > 1e-6:
            raise ValueError("Research weights must total 1.0")
        if any(w < 0 for w in self.weights.values()):
            raise ValueError("Research weights cannot be negative")

    def evaluate(self, product: ProductResearch) -> ResearchResult:
        scores = {
            "demand": product.demand_score,
            "competition": product.competition_score,
            "trend": product.trend_score,
        }

        # Collect missing fields before validation
        missing = [name for name, value in scores.items() if value is None]

        # Validate any supplied scores
        for name, value in scores.items():
            if value is not None and not (0 <= value <= 100):
                raise ValueError(f"{name} score must be between 0 and 100")

        if missing:
            return ResearchResult(
                product_id=product.product_id,
                opportunity_score=0.0,
                rating="INSUFFICIENT DATA",
                data_verified=product.data_verified,
                missing_fields=missing,
            )

        raw = sum(scores[name] * self.weights[name] for name in scores)
        score = round(raw, 2)

        if score >= 75:
            rating = "HIGH OPPORTUNITY"
        elif score >= 55:
            rating = "MODERATE OPPORTUNITY"
        elif score >= 35:
            rating = "LOW OPPORTUNITY"
        else:
            rating = "WEAK OPPORTUNITY"

        return ResearchResult(
            product_id=product.product_id,
            opportunity_score=score,
            rating=rating,
            data_verified=product.data_verified,
            missing_fields=[],
        )

    def rank_products(self, products: list[ProductResearch]) -> list[ResearchResult]:
        """Evaluate all products and return them sorted by opportunity score, highest first."""
        results = [self.evaluate(p) for p in products]
        return sorted(results, key=lambda r: r.opportunity_score, reverse=True)
