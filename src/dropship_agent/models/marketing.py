"""
Marketing Intelligence models for the AI Dropshipping Agent.

Five layers
-----------
MarketingInput              Full context passed to MarketingIntelligenceService.
AudienceProfile             Who the product is for and why they buy.
ChannelRecommendation       Which marketing channels suit this product and why.
PositioningRecommendation   Value proposition, differentiators, messaging themes.
MarketingIntelligence       Full output of one analyse() call.
CampaignMetrics             Operator-supplied performance data for one campaign.
PerformanceReport           Computed metrics, rating and rule-based recommendations.

Design rules
------------
- None always means "not set / not available".
- MarketingFlag distinguishes AI-generated content from derived arithmetic.
- No live advertising, automatic spending or external platform integration.
- Competitor analysis only uses information explicitly supplied by the operator.
  The service never invents competitors, prices, market shares or statistics.
- Human review is required before acting on any intelligence output.
- Metric denominators are checked before division; zero denominators never
  produce calculated ratios.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .opportunity import OpportunityResult
from .research import ResearchResult
from .content import ContentChannel, ContentTone, GeneratedContent


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class AudienceConfidence(str, Enum):
    """
    How well-grounded the audience profile is.

    DERIVED  — drawn directly from ResearchResult / OpportunityResult fields.
    INFERRED — reasonable inference from product category and name.
    ASSUMED  — operator-supplied assumption, not validated against data.
    UNKNOWN  — no basis available; profile is speculative.
    """
    DERIVED  = "DERIVED"
    INFERRED = "INFERRED"
    ASSUMED  = "ASSUMED"
    UNKNOWN  = "UNKNOWN"


class ChannelSuitability(str, Enum):
    HIGH    = "HIGH"
    MEDIUM  = "MEDIUM"
    LOW     = "LOW"
    UNKNOWN = "UNKNOWN"


class MarketingFlag(str, Enum):
    """
    Provenance of a marketing intelligence field.

    AI_GENERATED  — produced by the AI provider from the supplied context.
    DERIVED       — calculated deterministically from upstream result fields.
    OPERATOR      — supplied directly by the operator without AI processing.
    MISSING       — field could not be populated; value is empty / None.
    """
    AI_GENERATED = "AI_GENERATED"
    DERIVED      = "DERIVED"
    OPERATOR     = "OPERATOR"
    MISSING      = "MISSING"


# ---------------------------------------------------------------------------
# MarketingInput
# ---------------------------------------------------------------------------

@dataclass
class MarketingInput:
    """
    Full context passed to MarketingIntelligenceService.analyse().

    Fields
    ------
    product_id              : Matches Product.id.
    product_name            : Required.
    product_category        : Optional; improves relevance.
    product_description     : Operator-supplied; may be empty.
    known_features          : Confirmed features; differentiators drawn from these only.
    selling_price_usd       : Optional; absence is noted.
    research_result         : From ProductResearcher (Step 3).
    opportunity_result      : From ProductOpportunityEvaluator (Step 5).
    generated_content       : From ProductContentGenerator (Step 6); used to avoid
                              repeating channel work already done.
    target_market           : Operator-supplied geography or segment, e.g. "UK".
    operator_audience_notes : Operator's existing audience assumptions.
    competitor_evidence     : Operator-supplied competitor information only.
                              The service never invents competitors.
    analyse_audience        : Whether to generate an audience profile.
    analyse_channels        : Whether to generate channel recommendations.
    analyse_positioning     : Whether to generate positioning recommendations.
    analyse_competitors     : Explicit opt-in; only uses competitor_evidence supplied.
    data_verified           : True only if the operator has confirmed product data.
    """
    product_id: str
    product_name: str = ""
    product_category: str = ""
    product_description: str = ""
    known_features: list = field(default_factory=list)
    selling_price_usd: Optional[float] = None

    # Upstream results
    research_result: Optional[ResearchResult] = None
    opportunity_result: Optional[OpportunityResult] = None
    generated_content: Optional[GeneratedContent] = None

    # Operator context
    target_market: str = ""
    operator_audience_notes: str = ""
    competitor_evidence: list = field(default_factory=list)   # list[str]

    # Analysis flags
    analyse_audience: bool = True
    analyse_channels: bool = True
    analyse_positioning: bool = True
    analyse_competitors: bool = False   # explicit opt-in

    data_verified: bool = False


# ---------------------------------------------------------------------------
# Sub-result: AudienceProfile
# ---------------------------------------------------------------------------

@dataclass
class AudienceProfile:
    """
    Who the product is for and what motivates them to buy.

    primary_segment     : e.g. "outdoor enthusiasts aged 25–45".
    secondary_segments  : Additional audience segments.
    buying_motivations  : Why this audience buys this type of product.
    pain_points         : Problems this product addresses.
    confidence          : How well-grounded the profile is.
    basis               : One sentence explaining the evidence used.
    flag                : Provenance (AI_GENERATED, DERIVED, etc.).
    """
    primary_segment: str = ""
    secondary_segments: list = field(default_factory=list)
    buying_motivations: list = field(default_factory=list)
    pain_points: list = field(default_factory=list)
    confidence: AudienceConfidence = AudienceConfidence.UNKNOWN
    basis: str = ""
    flag: MarketingFlag = MarketingFlag.AI_GENERATED


# ---------------------------------------------------------------------------
# Sub-result: ChannelRecommendation
# ---------------------------------------------------------------------------

@dataclass
class ChannelRecommendation:
    """
    Suitability assessment for one marketing channel.

    channel          : Reuses ContentChannel from Step 6 — no new enum.
    suitability      : HIGH / MEDIUM / LOW / UNKNOWN.
    rationale        : Why this channel is or is not suitable.
    suggested_format : e.g. "carousel ads", "sponsored posts".
    flag             : Provenance.
    """
    channel: ContentChannel = ContentChannel.PRODUCT_LISTING
    suitability: ChannelSuitability = ChannelSuitability.UNKNOWN
    rationale: str = ""
    suggested_format: str = ""
    flag: MarketingFlag = MarketingFlag.AI_GENERATED


# ---------------------------------------------------------------------------
# Sub-result: PositioningRecommendation
# ---------------------------------------------------------------------------

@dataclass
class PositioningRecommendation:
    """
    Value proposition, differentiators and messaging recommendations.

    value_proposition           : Core customer benefit in one sentence.
    differentiators             : What sets the product apart.
                                  Drawn from known_features only — never invented.
    messaging_themes            : 2–4 campaign themes to test.
    tone_recommendation         : Reuses ContentTone from Step 6.
    competitor_positioning_notes: Generic positioning commentary only.
                                  Real competitor names only if supplied via
                                  competitor_evidence; never fabricated.
    flag                        : Provenance.
    """
    value_proposition: str = ""
    differentiators: list = field(default_factory=list)
    messaging_themes: list = field(default_factory=list)
    tone_recommendation: ContentTone = ContentTone.PROFESSIONAL
    competitor_positioning_notes: str = ""
    flag: MarketingFlag = MarketingFlag.AI_GENERATED


# ---------------------------------------------------------------------------
# Full output: MarketingIntelligence
# ---------------------------------------------------------------------------

@dataclass
class MarketingIntelligence:
    """
    Full output of MarketingIntelligenceService.analyse().

    Sub-results
    -----------
    audience_profile            : AudienceProfile or None.
    channel_recommendations     : list of ChannelRecommendation.
    positioning                 : PositioningRecommendation or None.

    Derived fields (no AI call)
    ---------------------------
    recommended_primary_channel : Best channel derived from OpportunityResult scores.
    campaign_strategy_summary   : 2–4 sentence plain-English summary.
    key_messages                : Top 3–5 messages to test.

    Transparency
    ------------
    missing_information         : Fields absent from MarketingInput that would
                                  improve quality.
    assumptions                 : What the AI inferred vs what was supplied.
    warnings                    : Non-fatal issues (e.g. competitor data absent).

    Provenance
    ----------
    provider_used               : Which AIProvider was used.
    data_verified               : Reflects MarketingInput.data_verified.
    generation_failed           : True if the AI call failed completely.
    failure_reason              : Explanation when generation_failed is True.
    """
    product_id: str

    audience_profile: Optional[AudienceProfile] = None
    channel_recommendations: list = field(default_factory=list)
    positioning: Optional[PositioningRecommendation] = None

    recommended_primary_channel: Optional[ContentChannel] = None
    campaign_strategy_summary: str = ""
    key_messages: list = field(default_factory=list)

    missing_information: list = field(default_factory=list)
    assumptions: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    provider_used: str = ""
    data_verified: bool = False
    generation_failed: bool = False
    failure_reason: str = ""


# ---------------------------------------------------------------------------
# Performance analysis input: CampaignMetrics
# ---------------------------------------------------------------------------

@dataclass
class CampaignMetrics:
    """
    Operator-supplied performance data for one campaign period.

    All metric fields are Optional — None means the data was not provided.
    Derived fields (ctr_pct, roas, etc.) are None on input and are populated
    by MarketingPerformanceAnalyser.

    Validation rules (enforced in __post_init__)
    --------------------------------------------
    - Negative values are rejected (ValueError).
    - Zero impressions with non-zero clicks is an inconsistent state.
      It is allowed but flagged — no CTR will be calculated.
    - Zero spend with non-zero conversions is allowed; ROAS will not be
      calculated (noted in PerformanceReport.missing_metrics).
    """
    product_id: str
    channel: ContentChannel
    period_label: str   # e.g. "Week 1", "2026-11"

    # Raw operator-supplied metrics
    impressions: Optional[int] = None
    clicks: Optional[int] = None
    conversions: Optional[int] = None
    spend_usd: Optional[float] = None
    revenue_usd: Optional[float] = None

    # Derived — populated by MarketingPerformanceAnalyser, not by the caller
    ctr_pct: Optional[float] = None
    conversion_rate_pct: Optional[float] = None
    roas: Optional[float] = None
    cost_per_click_usd: Optional[float] = None
    cost_per_conversion_usd: Optional[float] = None

    def __post_init__(self) -> None:
        int_fields = {
            "impressions": self.impressions,
            "clicks": self.clicks,
            "conversions": self.conversions,
        }
        float_fields = {
            "spend_usd": self.spend_usd,
            "revenue_usd": self.revenue_usd,
        }
        for name, value in int_fields.items():
            if value is not None and value < 0:
                raise ValueError(f"{name} cannot be negative, got {value}")
        for name, value in float_fields.items():
            if value is not None and value < 0:
                raise ValueError(f"{name} cannot be negative, got {value}")


# ---------------------------------------------------------------------------
# Performance analysis output: PerformanceReport
# ---------------------------------------------------------------------------

@dataclass
class PerformanceReport:
    """
    Output of MarketingPerformanceAnalyser.analyse().

    computed_metrics    : CampaignMetrics with derived fields populated.
    performance_rating  : "STRONG" / "ACCEPTABLE" / "POOR" / "INSUFFICIENT DATA".
    observations        : Factual bullets based on computed numbers.
                          e.g. "CTR of 2.4% exceeds the 2.0% STRONG threshold."
    recommendations     : Actionable suggestions derived from the numbers
                          using transparent rules (no AI provider required).
    missing_metrics     : Metric names that were None and prevented full analysis.
    data_verified       : Reflects whether the input metrics were confirmed.
    """
    product_id: str
    channel: ContentChannel
    period_label: str

    computed_metrics: CampaignMetrics = field(
        default_factory=lambda: CampaignMetrics(
            product_id="", channel=ContentChannel.PRODUCT_LISTING, period_label=""
        )
    )

    performance_rating: str = "INSUFFICIENT DATA"
    observations: list = field(default_factory=list)
    recommendations: list = field(default_factory=list)
    missing_metrics: list = field(default_factory=list)
    data_verified: bool = False
