"""
AI Dropshipping Agent — local preview API.

Runs all seven pipeline modules behind a FastAPI server.
Interactive docs available at http://localhost:8000/docs

Start with:
    .venv\\Scripts\\python.exe -m uvicorn src.dropship_agent.app:app --reload
"""

from __future__ import annotations

from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .models.research import ProductResearch
from .models.supplier import SupplierResearch
from .models.opportunity import OpportunityInput
from .models.content import ContentInput, ContentRequest, ContentType, ContentChannel, ContentTone
from .models.marketing import MarketingInput, CampaignMetrics, ContentChannel as MktChannel

from .services.researcher import ProductResearcher
from .services.supplier_researcher import SupplierResearcher
from .services.pricing import calculate_pricing
from .services.opportunity_evaluator import ProductOpportunityEvaluator
from .services.content_generator import ProductContentGenerator
from .services.marketing_intelligence import MarketingIntelligenceService, MarketingPerformanceAnalyser
from .services.ai_providers.mock_provider import MockProvider

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="AI Dropshipping Agent",
    description=(
        "Local preview of the AI Dropshipping Agent pipeline.\n\n"
        "**Modules available:**\n"
        "- `/health` — service status\n"
        "- `/research/product` — Step 3: Product Researcher\n"
        "- `/pricing` — Step 2: Pricing Engine\n"
        "- `/research/suppliers` — Step 4: Supplier Researcher\n"
        "- `/evaluate/opportunity` — Step 5: Opportunity Evaluator\n"
        "- `/generate/content` — Step 6: Content Generator (MockProvider)\n"
        "- `/analyse/marketing` — Step 7: Marketing Intelligence (MockProvider)\n"
        "- `/analyse/performance` — Step 7: Campaign Performance Analyser\n"
    ),
    version="0.7.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve the frontend dashboard
import os as _os
_frontend_dir = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.dirname(
    _os.path.abspath(__file__)))), "frontend")
if _os.path.isdir(_frontend_dir):
    app.mount("/static", StaticFiles(directory=_frontend_dir), name="static")

    @app.get("/", include_in_schema=False)
    def dashboard():
        return FileResponse(_os.path.join(_frontend_dir, "index.html"))

# Shared instances
_researcher  = ProductResearcher()
_supplier_r  = SupplierResearcher()
_evaluator   = ProductOpportunityEvaluator()
_generator   = ProductContentGenerator(provider=MockProvider())
_mkt_svc     = None   # created lazily — requires marketing module import
_perf        = MarketingPerformanceAnalyser()


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class ProductResearchRequest(BaseModel):
    product_id: str
    demand_score: Optional[float] = None
    competition_score: Optional[float] = None
    trend_score: Optional[float] = None
    data_verified: bool = False


class PricingRequest(BaseModel):
    supplier_cost: float
    shipping_cost: float = 0.0
    other_costs: float = 0.0
    selling_price: float


class SupplierResearchRequest(BaseModel):
    supplier_id: str
    unit_cost_usd: Optional[float] = None
    currency: str = "USD"
    availability: str = "UNKNOWN"
    has_tracked_shipping: Optional[bool] = None
    min_delivery_days: Optional[int] = None
    max_delivery_days: Optional[int] = None
    shipping_cost_usd: Optional[float] = None
    platform_rating: Optional[float] = None
    review_count: Optional[int] = None
    years_active: Optional[int] = None
    return_policy_available: Optional[bool] = None
    minimum_order_quantity: int = 1
    cost_includes_shipping: Optional[bool] = None
    fulfilment_type: str = "UNKNOWN"
    data_verified: bool = False


class SupplierCompareRequest(BaseModel):
    product_id: str
    suppliers: list[SupplierResearchRequest]


class OpportunityRequest(BaseModel):
    product_id: str
    research_opportunity_score: Optional[float] = None
    research_rating: Optional[str] = None
    best_unit_cost_usd: Optional[float] = None
    best_supplier_overall_score: Optional[float] = None
    best_supplier_recommendation: Optional[str] = None
    selling_price_usd: Optional[float] = None
    other_costs_usd: float = 0.0
    currency: str = "USD"


class ContentGenRequest(BaseModel):
    product_id: str
    product_name: str
    product_category: str = ""
    product_description: str = ""
    known_features: list[str] = []
    selling_price_usd: Optional[float] = None
    content_types: list[str] = ["PRODUCT_TITLE", "SHORT_SUMMARY", "BULLET_POINTS",
                                 "SEO_KEYWORDS", "META_DESCRIPTION"]
    channel: str = "PRODUCT_LISTING"
    tone: str = "PROFESSIONAL"
    variations: int = 1


class MarketingAnalyseRequest(BaseModel):
    product_id: str
    product_name: str
    product_category: str = ""
    known_features: list[str] = []
    selling_price_usd: Optional[float] = None
    target_market: str = ""
    operator_audience_notes: str = ""
    market_score: Optional[float] = None
    opportunity_classification: Optional[str] = None


class PerformanceRequest(BaseModel):
    product_id: str
    channel: str = "PAID_ADS"
    period_label: str = "Period 1"
    impressions: Optional[int] = None
    clicks: Optional[int] = None
    conversions: Optional[int] = None
    spend_usd: Optional[float] = None
    revenue_usd: Optional[float] = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health", tags=["System"])
def health():
    return {
        "status": "running",
        "version": "0.7.0",
        "modules": [
            "ProductResearcher",
            "PricingEngine",
            "SupplierResearcher",
            "ProductOpportunityEvaluator",
            "ProductContentGenerator (MockProvider)",
            "MarketingIntelligenceService (MockProvider)",
            "MarketingPerformanceAnalyser",
        ],
        "tests_passing": 321,
        "note": "Using MockProvider — no API key required for content and marketing.",
    }


@app.post("/research/product", tags=["Step 3 — Product Researcher"])
def research_product(req: ProductResearchRequest):
    product = ProductResearch(
        product_id=req.product_id,
        demand_score=req.demand_score,
        competition_score=req.competition_score,
        trend_score=req.trend_score,
        data_verified=req.data_verified,
    )
    result = _researcher.evaluate(product)
    return {
        "product_id": result.product_id,
        "opportunity_score": result.opportunity_score,
        "rating": result.rating,
        "data_verified": result.data_verified,
        "missing_fields": result.missing_fields,
    }


@app.post("/research/products/rank", tags=["Step 3 — Product Researcher"])
def rank_products(products: list[ProductResearchRequest]):
    researched = [
        ProductResearch(
            product_id=p.product_id,
            demand_score=p.demand_score,
            competition_score=p.competition_score,
            trend_score=p.trend_score,
            data_verified=p.data_verified,
        )
        for p in products
    ]
    ranked = _researcher.rank_products(researched)
    return [
        {
            "product_id": r.product_id,
            "opportunity_score": r.opportunity_score,
            "rating": r.rating,
            "missing_fields": r.missing_fields,
        }
        for r in ranked
    ]


@app.post("/pricing", tags=["Step 2 — Pricing Engine"])
def pricing(req: PricingRequest):
    result = calculate_pricing(
        supplier_cost=req.supplier_cost,
        shipping_cost=req.shipping_cost,
        other_costs=req.other_costs,
        selling_price=req.selling_price,
    )
    return {
        "total_landed_cost": result.total_landed_cost,
        "gross_profit": result.gross_profit,
        "gross_margin_pct": result.gross_margin_pct,
        "is_viable": result.is_viable,
    }


@app.post("/research/suppliers", tags=["Step 4 — Supplier Researcher"])
def compare_suppliers(req: SupplierCompareRequest):
    suppliers = [
        SupplierResearch(
            supplier_id=s.supplier_id,
            unit_cost_usd=s.unit_cost_usd,
            currency=s.currency,
            availability=s.availability,
            has_tracked_shipping=s.has_tracked_shipping,
            min_delivery_days=s.min_delivery_days,
            max_delivery_days=s.max_delivery_days,
            shipping_cost_usd=s.shipping_cost_usd,
            platform_rating=s.platform_rating,
            review_count=s.review_count,
            years_active=s.years_active,
            return_policy_available=s.return_policy_available,
            minimum_order_quantity=s.minimum_order_quantity,
            cost_includes_shipping=s.cost_includes_shipping,
            fulfilment_type=s.fulfilment_type,
            data_verified=s.data_verified,
        )
        for s in req.suppliers
    ]
    result = _supplier_r.compare(suppliers, product_id=req.product_id)
    return {
        "product_id": result.product_id,
        "recommended_supplier_id": result.recommended_supplier_id,
        "best_unit_cost_usd": result.best_unit_cost_usd,
        "comparison_notes": result.comparison_notes,
        "ranked_evaluations": [
            {
                "supplier_id": e.supplier_id,
                "overall_score": e.overall_score,
                "reliability_score": e.reliability_score,
                "fulfilment_score": e.fulfilment_score,
                "cost_score": e.cost_score,
                "recommendation": e.recommendation,
                "disqualified": e.disqualified,
                "disqualification_reason": e.disqualification_reason,
                "missing_fields": e.missing_fields,
                "cost_score_note": e.cost_score_note,
            }
            for e in result.ranked_evaluations
        ],
    }


@app.post("/evaluate/opportunity", tags=["Step 5 — Opportunity Evaluator"])
def evaluate_opportunity(req: OpportunityRequest):
    from .models.research import ResearchResult
    from .models.supplier import SupplierEvaluation, SupplierComparisonResult

    research = None
    if req.research_opportunity_score is not None and req.research_rating:
        research = ResearchResult(
            product_id=req.product_id,
            opportunity_score=req.research_opportunity_score,
            rating=req.research_rating,
            data_verified=False,
        )

    supplier_comp = None
    if req.best_unit_cost_usd is not None and req.best_supplier_overall_score is not None:
        evalu = SupplierEvaluation(
            supplier_id="api-supplier",
            reliability_score=req.best_supplier_overall_score,
            fulfilment_score=req.best_supplier_overall_score,
            cost_score=req.best_supplier_overall_score,
            overall_score=req.best_supplier_overall_score,
            recommendation=req.best_supplier_recommendation or "ACCEPTABLE",
            data_verified=False,
        )
        supplier_comp = SupplierComparisonResult(
            product_id=req.product_id,
            ranked_evaluations=[evalu],
            recommended_supplier_id="api-supplier",
            best_unit_cost_usd=req.best_unit_cost_usd,
        )

    opp_input = OpportunityInput(
        product_id=req.product_id,
        research_result=research,
        supplier_comparison=supplier_comp,
        selling_price_usd=req.selling_price_usd,
        other_costs_usd=req.other_costs_usd,
        currency=req.currency,
    )
    result = _evaluator.evaluate(opp_input)
    return {
        "product_id": result.product_id,
        "overall_score": result.overall_score,
        "classification": result.classification,
        "market_score": result.market_score,
        "supplier_score": result.supplier_score,
        "pricing_score": result.pricing_score,
        "estimated_margin_pct": result.estimated_margin_pct,
        "is_viable": result.is_viable,
        "supplier_cost_usd": result.supplier_cost_usd,
        "strengths": result.strengths,
        "weaknesses": result.weaknesses,
        "risks": result.risks,
        "missing_information": result.missing_information,
        "recommendation_basis": result.recommendation_basis,
    }


@app.post("/generate/content", tags=["Step 6 — Content Generator"])
def generate_content(req: ContentGenRequest):
    try:
        channel = ContentChannel(req.channel)
    except ValueError:
        channel = ContentChannel.PRODUCT_LISTING
    try:
        tone = ContentTone(req.tone)
    except ValueError:
        tone = ContentTone.PROFESSIONAL

    requests = []
    for ct_str in req.content_types:
        try:
            ct = ContentType(ct_str)
            requests.append(ContentRequest(
                content_type=ct,
                channel=channel,
                tone=tone,
                variations=req.variations,
            ))
        except ValueError:
            pass

    inp = ContentInput(
        product_id=req.product_id,
        product_name=req.product_name,
        product_category=req.product_category,
        product_description=req.product_description,
        known_features=req.known_features,
        selling_price_usd=req.selling_price_usd,
        requests=requests,
    )
    result = _generator.generate(inp)
    return {
        "product_id": result.product_id,
        "provider_used": result.provider_used,
        "generation_failed": result.generation_failed,
        "failure_reason": result.failure_reason,
        "missing_product_information": result.missing_product_information,
        "accuracy_warnings": result.accuracy_warnings,
        "items": [
            {
                "content_type": i.content_type.value,
                "channel": i.channel.value,
                "tone": i.tone.value,
                "variation_index": i.variation_index,
                "text": i.text,
                "text_list": i.text_list,
                "char_count": i.char_count,
                "verification_flag": i.verification_flag.value,
                "grounding_notes": i.grounding_notes,
            }
            for i in result.items
        ],
    }


@app.post("/analyse/marketing", tags=["Step 7 — Marketing Intelligence"])
def analyse_marketing(req: MarketingAnalyseRequest):
    global _mkt_svc
    if _mkt_svc is None:
        from .services.marketing_intelligence import MarketingIntelligenceService
        from .services.ai_providers.mock_provider import MockProvider as MP

        class _MarketingMock(MP):
            @property
            def name(self):
                return "marketing-mock"
            def complete(self, prompt, max_tokens=500):
                import re
                m = re.search(r"<<PRODUCT_NAME>>(.*?)<</PRODUCT_NAME>>", prompt)
                name = m.group(1).strip() if m else req.product_name
                return (
                    f"<<SECTION_AUDIENCE>>\n"
                    f"PRIMARY_SEGMENT: shoppers interested in {name}\n"
                    f"SECONDARY_SEGMENTS: gift buyers, enthusiasts\n"
                    f"BUYING_MOTIVATIONS: value for money, convenience, reliability\n"
                    f"PAIN_POINTS: difficulty finding good products online, high prices\n"
                    f"CONFIDENCE: INFERRED\n"
                    f"BASIS: Inferred from product name and category.\n"
                    f"<</SECTION_AUDIENCE>>\n\n"
                    f"<<SECTION_CHANNELS>>\n"
                    f"CHANNEL: PRODUCT_LISTING\n"
                    f"SUITABILITY: HIGH\n"
                    f"RATIONALE: Direct listing reaches buyers actively searching.\n"
                    f"SUGGESTED_FORMAT: standard product page\n"
                    f"---\n"
                    f"CHANNEL: SOCIAL_MEDIA\n"
                    f"SUITABILITY: MEDIUM\n"
                    f"RATIONALE: Social can build brand awareness.\n"
                    f"SUGGESTED_FORMAT: image posts with hashtags\n"
                    f"<</SECTION_CHANNELS>>\n\n"
                    f"<<SECTION_POSITIONING>>\n"
                    f"VALUE_PROPOSITION: {name} delivers quality at a fair price.\n"
                    f"DIFFERENTIATORS: quality, reliability, value\n"
                    f"MESSAGING_THEMES: quality and value, ease of use, trusted product\n"
                    f"TONE: PROFESSIONAL\n"
                    f"COMPETITOR_NOTES: Products in this category compete on price and reliability.\n"
                    f"<</SECTION_POSITIONING>>"
                )

        _mkt_svc = MarketingIntelligenceService(provider=_MarketingMock())

    from .models.marketing import MarketingInput as MI
    from .models.research import ResearchResult
    from .models.opportunity import OpportunityResult

    research = None
    if req.market_score is not None:
        research = ResearchResult(
            product_id=req.product_id,
            opportunity_score=req.market_score,
            rating="MODERATE OPPORTUNITY",
            data_verified=False,
        )

    opportunity = None
    if req.opportunity_classification and req.market_score is not None:
        opportunity = OpportunityResult(
            product_id=req.product_id,
            market_score=req.market_score,
            supplier_score=70.0,
            pricing_score=80.0,
            overall_score=req.market_score,
            classification=req.opportunity_classification,
            supplier_cost_usd=None,
            estimated_margin_pct=None,
            is_viable=None,
        )

    inp = MI(
        product_id=req.product_id,
        product_name=req.product_name,
        product_category=req.product_category,
        known_features=req.known_features,
        selling_price_usd=req.selling_price_usd,
        target_market=req.target_market,
        operator_audience_notes=req.operator_audience_notes,
        research_result=research,
        opportunity_result=opportunity,
    )
    result = _mkt_svc.analyse(inp)

    return {
        "product_id": result.product_id,
        "generation_failed": result.generation_failed,
        "failure_reason": result.failure_reason,
        "provider_used": result.provider_used,
        "recommended_primary_channel": (
            result.recommended_primary_channel.value
            if result.recommended_primary_channel else None
        ),
        "campaign_strategy_summary": result.campaign_strategy_summary,
        "key_messages": result.key_messages,
        "audience_profile": (
            {
                "primary_segment": result.audience_profile.primary_segment,
                "secondary_segments": result.audience_profile.secondary_segments,
                "buying_motivations": result.audience_profile.buying_motivations,
                "pain_points": result.audience_profile.pain_points,
                "confidence": result.audience_profile.confidence.value,
                "basis": result.audience_profile.basis,
            }
            if result.audience_profile else None
        ),
        "channel_recommendations": [
            {
                "channel": c.channel.value,
                "suitability": c.suitability.value,
                "rationale": c.rationale,
                "suggested_format": c.suggested_format,
            }
            for c in result.channel_recommendations
        ],
        "positioning": (
            {
                "value_proposition": result.positioning.value_proposition,
                "differentiators": result.positioning.differentiators,
                "messaging_themes": result.positioning.messaging_themes,
                "tone_recommendation": result.positioning.tone_recommendation.value,
                "competitor_positioning_notes": result.positioning.competitor_positioning_notes,
            }
            if result.positioning else None
        ),
        "missing_information": result.missing_information,
        "assumptions": result.assumptions,
        "warnings": result.warnings,
    }


@app.post("/analyse/performance", tags=["Step 7 — Marketing Intelligence"])
def analyse_performance(req: PerformanceRequest):
    from .models.content import ContentChannel as CC
    try:
        ch = CC(req.channel)
    except ValueError:
        ch = CC.PAID_ADS

    metrics = CampaignMetrics(
        product_id=req.product_id,
        channel=ch,
        period_label=req.period_label,
        impressions=req.impressions,
        clicks=req.clicks,
        conversions=req.conversions,
        spend_usd=req.spend_usd,
        revenue_usd=req.revenue_usd,
    )
    report = _perf.analyse(metrics)
    cm = report.computed_metrics
    return {
        "product_id": report.product_id,
        "channel": report.channel.value,
        "period_label": report.period_label,
        "performance_rating": report.performance_rating,
        "computed_metrics": {
            "impressions": cm.impressions,
            "clicks": cm.clicks,
            "conversions": cm.conversions,
            "spend_usd": cm.spend_usd,
            "revenue_usd": cm.revenue_usd,
            "ctr_pct": cm.ctr_pct,
            "conversion_rate_pct": cm.conversion_rate_pct,
            "roas": cm.roas,
            "cost_per_click_usd": cm.cost_per_click_usd,
            "cost_per_conversion_usd": cm.cost_per_conversion_usd,
        },
        "observations": report.observations,
        "recommendations": report.recommendations,
        "missing_metrics": report.missing_metrics,
    }
