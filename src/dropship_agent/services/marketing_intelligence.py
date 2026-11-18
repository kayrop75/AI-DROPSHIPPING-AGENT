"""
Marketing Intelligence service.

Two classes
-----------
MarketingIntelligenceService
    Uses an AIProvider (injected) to produce audience intelligence, channel
    recommendations and product positioning in a single structured AI call.
    Derives non-AI fields (recommended channel, missing info, assumptions)
    from upstream result objects without touching the provider.

MarketingPerformanceAnalyser
    Pure arithmetic + rule-based.  No AI provider required or accepted.
    Computes derived metrics (CTR, ROAS, CPC, etc.) and rates performance
    against published thresholds.

Design rules
------------
- One AI call per analyse() invocation covering all requested sections.
- Structured <<SECTION>> tags in the response allow deterministic parsing.
- Malformed sections are returned as empty / None with a warning, not a crash.
- Competitor analysis only uses information supplied in competitor_evidence.
  Real competitor names are never invented.
- Zero denominators are detected before division; ratios are left as None
  with a note in missing_metrics.
- No live advertising, automatic spending or external platform connections.
"""

from __future__ import annotations

import re
from typing import Optional

from ..models.content import AIProviderError, ContentChannel, ContentTone
from ..models.marketing import (
    AudienceConfidence,
    AudienceProfile,
    CampaignMetrics,
    ChannelRecommendation,
    ChannelSuitability,
    MarketingFlag,
    MarketingInput,
    MarketingIntelligence,
    PerformanceReport,
    PositioningRecommendation,
)
from .ai_providers.base import AIProvider


# ---------------------------------------------------------------------------
# Performance thresholds (transparent, no magic numbers buried in logic)
# ---------------------------------------------------------------------------

_CTR_STRONG      = 2.0   # %
_CTR_ACCEPTABLE  = 0.5   # %
_CVR_STRONG      = 3.0   # %
_CVR_ACCEPTABLE  = 1.0   # %
_ROAS_STRONG     = 3.0   # ×
_ROAS_ACCEPTABLE = 1.5   # ×

# Channel suitability keywords used in parsing
_SUITABILITY_MAP = {
    "high": ChannelSuitability.HIGH,
    "medium": ChannelSuitability.MEDIUM,
    "low": ChannelSuitability.LOW,
}

# Tone keywords used in parsing
_TONE_MAP = {
    "professional": ContentTone.PROFESSIONAL,
    "casual":       ContentTone.CASUAL,
    "enthusiastic": ContentTone.ENTHUSIASTIC,
    "minimalist":   ContentTone.MINIMALIST,
}

# Channel keywords used in parsing
_CHANNEL_MAP = {
    "product_listing": ContentChannel.PRODUCT_LISTING,
    "product listing": ContentChannel.PRODUCT_LISTING,
    "social_media":    ContentChannel.SOCIAL_MEDIA,
    "social media":    ContentChannel.SOCIAL_MEDIA,
    "paid_ads":        ContentChannel.PAID_ADS,
    "paid ads":        ContentChannel.PAID_ADS,
    "email":           ContentChannel.EMAIL,
    "seo":             ContentChannel.SEO,
}


class MarketingIntelligenceService:
    """
    Generates audience intelligence, channel recommendations and product
    positioning from product and opportunity context.

    Parameters
    ----------
    provider : AIProvider
        The AI backend to use.  Inject MarketingMockProvider for tests.
    """

    def __init__(self, provider: AIProvider) -> None:
        if not isinstance(provider, AIProvider):
            raise TypeError(
                f"provider must be an AIProvider instance, "
                f"got {type(provider).__name__}"
            )
        self._provider = provider

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyse(self, inp: MarketingInput) -> MarketingIntelligence:
        """
        Produce marketing intelligence for the product described in inp.

        Returns a MarketingIntelligence.  Never raises — failures are
        captured in generation_failed / failure_reason / warnings.
        """
        # --- Validate required field ---
        if not inp.product_name or not inp.product_name.strip():
            return MarketingIntelligence(
                product_id=inp.product_id,
                generation_failed=True,
                failure_reason="product_name is required but was empty.",
                provider_used=self._provider.name,
            )

        # --- Determine what to generate ---
        any_ai_work = (
            inp.analyse_audience
            or inp.analyse_channels
            or inp.analyse_positioning
        )

        missing_info = self._identify_missing(inp)
        assumptions: list[str] = []
        warnings: list[str] = []

        # --- Derived fields (no AI call needed) ---
        recommended_channel = self._derive_primary_channel(inp)

        if not any_ai_work:
            warnings.append(
                "No analysis types were enabled.  "
                "Set analyse_audience, analyse_channels or analyse_positioning to True."
            )
            return MarketingIntelligence(
                product_id=inp.product_id,
                recommended_primary_channel=recommended_channel,
                missing_information=missing_info,
                assumptions=assumptions,
                warnings=warnings,
                provider_used=self._provider.name,
                data_verified=inp.data_verified,
            )

        # --- Single structured AI call ---
        prompt = self._build_prompt(inp)
        try:
            raw_response = self._provider.complete(prompt, max_tokens=900)
        except AIProviderError as exc:
            return MarketingIntelligence(
                product_id=inp.product_id,
                generation_failed=True,
                failure_reason=f"AI provider error: {exc}",
                recommended_primary_channel=recommended_channel,
                missing_information=missing_info,
                provider_used=self._provider.name,
                data_verified=inp.data_verified,
            )

        # --- Parse structured response ---
        audience_profile   = None
        channel_recs: list = []
        positioning        = None

        if inp.analyse_audience:
            audience_profile, aud_warn = self._parse_audience(
                raw_response, inp
            )
            if aud_warn:
                warnings.append(aud_warn)

        if inp.analyse_channels:
            channel_recs, ch_warn = self._parse_channels(raw_response)
            if ch_warn:
                warnings.append(ch_warn)

        if inp.analyse_positioning:
            positioning, pos_warn = self._parse_positioning(
                raw_response, inp
            )
            if pos_warn:
                warnings.append(pos_warn)

        # --- Collect assumptions ---
        assumptions = self._collect_assumptions(inp, audience_profile, positioning)

        # --- Campaign summary ---
        summary, key_msgs = self._build_summary(inp, audience_profile,
                                                 channel_recs, positioning)

        return MarketingIntelligence(
            product_id=inp.product_id,
            audience_profile=audience_profile,
            channel_recommendations=channel_recs,
            positioning=positioning,
            recommended_primary_channel=recommended_channel,
            campaign_strategy_summary=summary,
            key_messages=key_msgs,
            missing_information=missing_info,
            assumptions=assumptions,
            warnings=warnings,
            provider_used=self._provider.name,
            data_verified=inp.data_verified,
        )

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    def _build_prompt(self, inp: MarketingInput) -> str:
        """
        Build a single structured prompt requesting all enabled analysis types.
        Tags:  <<SECTION_AUDIENCE>>, <<SECTION_CHANNELS>>, <<SECTION_POSITIONING>>.
        Each section must end with the matching closing tag.
        Unknown or omitted sections are ignored by the parser.
        """
        features_str = " | ".join(inp.known_features) if inp.known_features else "not provided"
        price_str    = f"${inp.selling_price_usd:.2f}" \
                       if inp.selling_price_usd is not None else "not provided"
        opp_cls      = inp.opportunity_result.classification \
                       if inp.opportunity_result else "not available"
        opp_score    = str(round(inp.opportunity_result.overall_score, 1)) \
                       if inp.opportunity_result else "not available"
        research_rtg = inp.research_result.rating \
                       if inp.research_result else "not available"
        mkt_score    = str(round(inp.research_result.opportunity_score, 1)) \
                       if inp.research_result else "not available"

        comp_block = ""
        if inp.analyse_competitors and inp.competitor_evidence:
            comp_block = (
                "\nCompetitor evidence (operator-supplied only — do not add other names):\n"
                + "\n".join(f"- {c}" for c in inp.competitor_evidence)
            )
        elif inp.analyse_competitors:
            comp_block = (
                "\nCompetitor analysis requested but no evidence supplied.  "
                "Provide generic positioning commentary only — do not name specific brands."
            )

        sections_requested = []
        if inp.analyse_audience:
            sections_requested.append(
                "<<SECTION_AUDIENCE>>\n"
                "Provide: PRIMARY_SEGMENT, SECONDARY_SEGMENTS (comma-separated), "
                "BUYING_MOTIVATIONS (comma-separated), PAIN_POINTS (comma-separated), "
                "CONFIDENCE (DERIVED/INFERRED/ASSUMED/UNKNOWN), BASIS (one sentence).\n"
                "Use only the product information provided above.\n"
                "<</SECTION_AUDIENCE>>"
            )
        if inp.analyse_channels:
            sections_requested.append(
                "<<SECTION_CHANNELS>>\n"
                "For each relevant channel from: PRODUCT_LISTING, SOCIAL_MEDIA, PAID_ADS, EMAIL, SEO\n"
                "Provide: CHANNEL, SUITABILITY (HIGH/MEDIUM/LOW), "
                "RATIONALE (one sentence), SUGGESTED_FORMAT (brief).\n"
                "Separate channels with ---\n"
                "<</SECTION_CHANNELS>>"
            )
        if inp.analyse_positioning:
            sections_requested.append(
                "<<SECTION_POSITIONING>>\n"
                "Provide: VALUE_PROPOSITION (one sentence), "
                "DIFFERENTIATORS (comma-separated, from known features only), "
                "MESSAGING_THEMES (comma-separated, 2-4 themes), "
                "TONE (PROFESSIONAL/CASUAL/ENTHUSIASTIC/MINIMALIST),"
                "COMPETITOR_NOTES (generic only, no invented brand names).\n"
                "<</SECTION_POSITIONING>>"
            )

        sections_block = "\n\n".join(sections_requested)

        lines = [
            "You are a marketing intelligence analyst specialising in e-commerce.",
            "Use only the information provided below.  "
            "Do not invent competitor names, statistics, certifications or product features.",
            "",
            f"<<PRODUCT_NAME>>{inp.product_name}<</PRODUCT_NAME>>",
            f"<<CATEGORY>>{inp.product_category or 'not provided'}<</CATEGORY>>",
            f"<<FEATURES>>{features_str}<</FEATURES>>",
            f"<<PRICE>>{price_str}<</PRICE>>",
            f"<<MARKET>>{inp.target_market or 'not specified'}<</MARKET>>",
            f"<<OPPORTUNITY_CLASS>>{opp_cls}<</OPPORTUNITY_CLASS>>",
            f"<<OPPORTUNITY_SCORE>>{opp_score}<</OPPORTUNITY_SCORE>>",
            f"<<RESEARCH_RATING>>{research_rtg}<</RESEARCH_RATING>>",
            f"<<MARKET_SCORE>>{mkt_score}<</MARKET_SCORE>>",
        ]
        if inp.operator_audience_notes:
            lines.append(
                f"<<AUDIENCE_NOTES>>{inp.operator_audience_notes}<</AUDIENCE_NOTES>>"
            )
        if inp.product_description:
            lines.append(
                f"<<DESCRIPTION>>{inp.product_description}<</DESCRIPTION>>"
            )
        if comp_block:
            lines.append(comp_block)

        lines += ["", "Respond using the following structured sections:", sections_block]
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_section(tag: str, text: str) -> str:
        """Extract content between <<TAG>> and <</TAG>>. Returns '' if absent."""
        m = re.search(
            rf"<<{tag}>>(.*?)<</{ tag}>>",
            text,
            re.DOTALL | re.IGNORECASE,
        )
        return m.group(1).strip() if m else ""

    @staticmethod
    def _extract_field(label: str, text: str) -> str:
        """
        Extract the value after 'LABEL:' or 'LABEL =' on a line.
        Returns '' if the label is not found.
        """
        m = re.search(
            rf"^\s*{re.escape(label)}\s*[:\=]\s*(.+)$",
            text,
            re.MULTILINE | re.IGNORECASE,
        )
        return m.group(1).strip() if m else ""

    @staticmethod
    def _split_csv(text: str) -> list[str]:
        """Split a comma-separated string into a cleaned list."""
        return [item.strip() for item in text.split(",") if item.strip()]

    def _parse_audience(
        self, response: str, inp: MarketingInput
    ) -> tuple[Optional[AudienceProfile], str]:
        """
        Parse <<SECTION_AUDIENCE>> from the response.
        Returns (AudienceProfile or None, warning string).
        """
        section = self._extract_section("SECTION_AUDIENCE", response)
        if not section:
            return None, (
                "SECTION_AUDIENCE missing from AI response.  "
                "Audience profile could not be populated."
            )

        primary    = self._extract_field("PRIMARY_SEGMENT", section)
        secondary  = self._split_csv(self._extract_field("SECONDARY_SEGMENTS", section))
        motivations = self._split_csv(self._extract_field("BUYING_MOTIVATIONS", section))
        pain_points = self._split_csv(self._extract_field("PAIN_POINTS", section))
        conf_raw   = self._extract_field("CONFIDENCE", section).upper()
        basis      = self._extract_field("BASIS", section)

        confidence = AudienceConfidence.UNKNOWN
        for member in AudienceConfidence:
            if member.value == conf_raw:
                confidence = member
                break

        # If operator supplied notes, upgrade minimum confidence
        if inp.operator_audience_notes and confidence == AudienceConfidence.UNKNOWN:
            confidence = AudienceConfidence.ASSUMED

        if not primary:
            return None, (
                "PRIMARY_SEGMENT not found in SECTION_AUDIENCE.  "
                "Audience profile is incomplete."
            )

        return AudienceProfile(
            primary_segment=primary,
            secondary_segments=secondary,
            buying_motivations=motivations,
            pain_points=pain_points,
            confidence=confidence,
            basis=basis or "Derived from product context.",
            flag=MarketingFlag.AI_GENERATED,
        ), ""

    def _parse_channels(
        self, response: str
    ) -> tuple[list[ChannelRecommendation], str]:
        """
        Parse <<SECTION_CHANNELS>> from the response.
        Returns (list of ChannelRecommendation, warning string).
        """
        section = self._extract_section("SECTION_CHANNELS", response)
        if not section:
            return [], (
                "SECTION_CHANNELS missing from AI response.  "
                "Channel recommendations could not be populated."
            )

        recs: list[ChannelRecommendation] = []
        # Channels are separated by ---
        blocks = re.split(r"\n\s*---\s*\n", section)
        for block in blocks:
            block = block.strip()
            if not block:
                continue
            ch_raw   = self._extract_field("CHANNEL", block).upper()
            suit_raw = self._extract_field("SUITABILITY", block).lower()
            rat      = self._extract_field("RATIONALE", block)
            fmt      = self._extract_field("SUGGESTED_FORMAT", block)

            channel = None
            for key, val in _CHANNEL_MAP.items():
                if key in ch_raw.lower():
                    channel = val
                    break
            if channel is None:
                continue   # skip unrecognised channel entries

            suitability = _SUITABILITY_MAP.get(suit_raw, ChannelSuitability.UNKNOWN)

            recs.append(ChannelRecommendation(
                channel=channel,
                suitability=suitability,
                rationale=rat or "No rationale provided.",
                suggested_format=fmt,
                flag=MarketingFlag.AI_GENERATED,
            ))

        if not recs:
            return [], (
                "No recognisable channels found in SECTION_CHANNELS.  "
                "Channel recommendations are empty."
            )
        return recs, ""

    def _parse_positioning(
        self, response: str, inp: MarketingInput
    ) -> tuple[Optional[PositioningRecommendation], str]:
        """
        Parse <<SECTION_POSITIONING>> from the response.
        Returns (PositioningRecommendation or None, warning string).
        """
        section = self._extract_section("SECTION_POSITIONING", response)
        if not section:
            return None, (
                "SECTION_POSITIONING missing from AI response.  "
                "Positioning recommendation could not be populated."
            )

        vp         = self._extract_field("VALUE_PROPOSITION", section)
        diffs      = self._split_csv(self._extract_field("DIFFERENTIATORS", section))
        themes     = self._split_csv(self._extract_field("MESSAGING_THEMES", section))
        tone_raw   = self._extract_field("TONE", section).lower()
        comp_notes = self._extract_field("COMPETITOR_NOTES", section)

        tone = _TONE_MAP.get(tone_raw, ContentTone.PROFESSIONAL)

        # Guardrail: differentiators must come from known_features only
        if inp.known_features:
            known_lower = [f.lower() for f in inp.known_features]
            filtered = [d for d in diffs if any(k in d.lower() for k in known_lower)]
            # If filtering removed everything, keep all (AI may have paraphrased)
            if filtered:
                diffs = filtered

        if not vp:
            return None, (
                "VALUE_PROPOSITION not found in SECTION_POSITIONING.  "
                "Positioning recommendation is incomplete."
            )

        return PositioningRecommendation(
            value_proposition=vp,
            differentiators=diffs,
            messaging_themes=themes,
            tone_recommendation=tone,
            competitor_positioning_notes=comp_notes,
            flag=MarketingFlag.AI_GENERATED,
        ), ""

    # ------------------------------------------------------------------
    # Derivation helpers (no AI call)
    # ------------------------------------------------------------------

    @staticmethod
    def _derive_primary_channel(inp: MarketingInput) -> Optional[ContentChannel]:
        """
        Recommend a primary channel deterministically from upstream scores.
        Returns None when insufficient context is available.
        """
        if inp.opportunity_result is None:
            return None
        ms = inp.opportunity_result.market_score
        if ms >= 70:
            return ContentChannel.PAID_ADS
        if ms >= 50:
            return ContentChannel.SOCIAL_MEDIA
        return ContentChannel.PRODUCT_LISTING

    @staticmethod
    def _identify_missing(inp: MarketingInput) -> list[str]:
        missing = []
        if not inp.product_description:
            missing.append("product_description")
        if not inp.known_features:
            missing.append("known_features")
        if inp.selling_price_usd is None:
            missing.append("selling_price_usd")
        if inp.research_result is None:
            missing.append("research_result")
        if inp.opportunity_result is None:
            missing.append("opportunity_result")
        return missing

    @staticmethod
    def _collect_assumptions(
        inp: MarketingInput,
        audience: Optional[AudienceProfile],
        positioning: Optional[PositioningRecommendation],
    ) -> list[str]:
        assumptions = []
        if inp.operator_audience_notes:
            assumptions.append(
                f"Audience notes supplied by operator: '{inp.operator_audience_notes}'"
            )
        if audience and audience.confidence in (
            AudienceConfidence.INFERRED, AudienceConfidence.UNKNOWN
        ):
            assumptions.append(
                "Audience profile inferred from product category and name "
                "— not validated against market data."
            )
        if positioning and not inp.known_features:
            assumptions.append(
                "Differentiators could not be drawn from known_features "
                "(none supplied) — positioning may be generic."
            )
        if inp.analyse_competitors and not inp.competitor_evidence:
            assumptions.append(
                "Competitor analysis requested but no evidence supplied.  "
                "Competitor notes are generic positioning commentary only."
            )
        return assumptions

    @staticmethod
    def _build_summary(
        inp: MarketingInput,
        audience: Optional[AudienceProfile],
        channels: list,
        positioning: Optional[PositioningRecommendation],
    ) -> tuple[str, list[str]]:
        """Build a plain-English summary and key messages from parsed results."""
        parts = []
        key_msgs: list[str] = []

        if audience and audience.primary_segment:
            parts.append(
                f"Primary audience: {audience.primary_segment}."
            )

        top_channel = next(
            (c for c in channels if c.suitability == ChannelSuitability.HIGH),
            channels[0] if channels else None,
        )
        if top_channel:
            parts.append(
                f"Recommended primary channel: {top_channel.channel.value} "
                f"({top_channel.suitability.value} suitability)."
            )

        if positioning and positioning.value_proposition:
            parts.append(
                f"Core value proposition: {positioning.value_proposition}"
            )
            key_msgs = positioning.messaging_themes[:5]

        if inp.opportunity_result:
            cls = inp.opportunity_result.classification
            parts.append(
                f"Opportunity classification: {cls}."
            )

        return "  ".join(parts), key_msgs


# ---------------------------------------------------------------------------
# MarketingPerformanceAnalyser — pure arithmetic, no AI provider
# ---------------------------------------------------------------------------

class MarketingPerformanceAnalyser:
    """
    Computes derived campaign metrics and rates performance.

    No AI provider.  All logic is deterministic arithmetic and
    transparent threshold rules.

    Performance thresholds
    ----------------------
    CTR   : STRONG >= 2.0%,  ACCEPTABLE >= 0.5%,  else POOR
    CVR   : STRONG >= 3.0%,  ACCEPTABLE >= 1.0%,  else POOR
    ROAS  : STRONG >= 3.0×,  ACCEPTABLE >= 1.5×,  else POOR

    Overall rating = majority across available metrics.
    INSUFFICIENT DATA if fewer than two metrics are computable.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyse(self, metrics: CampaignMetrics) -> PerformanceReport:
        """Compute all derived metrics and return a PerformanceReport."""
        computed, missing = self._compute(metrics)
        ratings, observations = self._rate(computed, missing)
        overall = self._overall_rating(ratings)
        recommendations = self._recommend(computed, overall, missing)

        return PerformanceReport(
            product_id=metrics.product_id,
            channel=metrics.channel,
            period_label=metrics.period_label,
            computed_metrics=computed,
            performance_rating=overall,
            observations=observations,
            recommendations=recommendations,
            missing_metrics=missing,
            data_verified=False,
        )

    def compare(
        self, metrics_list: list[CampaignMetrics]
    ) -> list[PerformanceReport]:
        """Analyse each CampaignMetrics and return one report per input."""
        return [self.analyse(m) for m in metrics_list]

    # ------------------------------------------------------------------
    # Metric computation
    # ------------------------------------------------------------------

    @staticmethod
    def _compute(
        m: CampaignMetrics,
    ) -> tuple[CampaignMetrics, list[str]]:
        """
        Return a new CampaignMetrics with derived fields populated,
        and a list of fields that could not be computed.
        """
        missing: list[str] = []

        # CTR — clicks / impressions
        ctr = None
        if m.clicks is not None and m.impressions is not None:
            if m.impressions == 0:
                if m.clicks > 0:
                    missing.append(
                        "ctr_pct (impressions=0 with clicks>0 is inconsistent data)"
                    )
                else:
                    ctr = 0.0
            else:
                ctr = round((m.clicks / m.impressions) * 100, 4)
        else:
            missing.append("ctr_pct")

        # Conversion rate — conversions / clicks
        cvr = None
        if m.conversions is not None and m.clicks is not None:
            if m.clicks == 0:
                if m.conversions > 0:
                    missing.append(
                        "conversion_rate_pct (clicks=0 with conversions>0 is inconsistent)"
                    )
                else:
                    cvr = 0.0
            else:
                cvr = round((m.conversions / m.clicks) * 100, 4)
        else:
            missing.append("conversion_rate_pct")

        # ROAS — revenue / spend
        roas = None
        if m.revenue_usd is not None and m.spend_usd is not None:
            if m.spend_usd == 0:
                missing.append("roas (spend_usd=0, ratio undefined)")
            else:
                roas = round(m.revenue_usd / m.spend_usd, 4)
        else:
            missing.append("roas")

        # CPC — spend / clicks
        cpc = None
        if m.spend_usd is not None and m.clicks is not None:
            if m.clicks == 0:
                missing.append("cost_per_click_usd (clicks=0)")
            else:
                cpc = round(m.spend_usd / m.clicks, 4)
        else:
            missing.append("cost_per_click_usd")

        # CPA — spend / conversions
        cpa = None
        if m.spend_usd is not None and m.conversions is not None:
            if m.conversions == 0:
                missing.append("cost_per_conversion_usd (conversions=0)")
            else:
                cpa = round(m.spend_usd / m.conversions, 4)
        else:
            missing.append("cost_per_conversion_usd")

        computed = CampaignMetrics(
            product_id=m.product_id,
            channel=m.channel,
            period_label=m.period_label,
            impressions=m.impressions,
            clicks=m.clicks,
            conversions=m.conversions,
            spend_usd=m.spend_usd,
            revenue_usd=m.revenue_usd,
            ctr_pct=ctr,
            conversion_rate_pct=cvr,
            roas=roas,
            cost_per_click_usd=cpc,
            cost_per_conversion_usd=cpa,
        )
        return computed, missing

    # ------------------------------------------------------------------
    # Rating helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _rate(
        m: CampaignMetrics, missing: list[str]
    ) -> tuple[list[str], list[str]]:
        """
        Return a list of individual ratings and a list of observation bullets.
        """
        ratings: list[str] = []
        obs: list[str]     = []

        if m.ctr_pct is not None:
            if m.ctr_pct >= _CTR_STRONG:
                ratings.append("STRONG")
                obs.append(f"CTR {m.ctr_pct:.2f}% — above {_CTR_STRONG}% (STRONG threshold).")
            elif m.ctr_pct >= _CTR_ACCEPTABLE:
                ratings.append("ACCEPTABLE")
                obs.append(f"CTR {m.ctr_pct:.2f}% — above {_CTR_ACCEPTABLE}% (ACCEPTABLE threshold).")
            else:
                ratings.append("POOR")
                obs.append(f"CTR {m.ctr_pct:.2f}% — below {_CTR_ACCEPTABLE}% (POOR).")

        if m.conversion_rate_pct is not None:
            if m.conversion_rate_pct >= _CVR_STRONG:
                ratings.append("STRONG")
                obs.append(
                    f"Conversion rate {m.conversion_rate_pct:.2f}% — above {_CVR_STRONG}%."
                )
            elif m.conversion_rate_pct >= _CVR_ACCEPTABLE:
                ratings.append("ACCEPTABLE")
                obs.append(
                    f"Conversion rate {m.conversion_rate_pct:.2f}% — above {_CVR_ACCEPTABLE}%."
                )
            else:
                ratings.append("POOR")
                obs.append(
                    f"Conversion rate {m.conversion_rate_pct:.2f}% — below {_CVR_ACCEPTABLE}%."
                )

        if m.roas is not None:
            if m.roas >= _ROAS_STRONG:
                ratings.append("STRONG")
                obs.append(f"ROAS {m.roas:.2f}× — above {_ROAS_STRONG}× (STRONG).")
            elif m.roas >= _ROAS_ACCEPTABLE:
                ratings.append("ACCEPTABLE")
                obs.append(f"ROAS {m.roas:.2f}× — above {_ROAS_ACCEPTABLE}× (ACCEPTABLE).")
            else:
                ratings.append("POOR")
                obs.append(f"ROAS {m.roas:.2f}× — below {_ROAS_ACCEPTABLE}× (POOR).")

        return ratings, obs

    @staticmethod
    def _overall_rating(ratings: list[str]) -> str:
        if len(ratings) < 2:
            return "INSUFFICIENT DATA"
        counts = {r: ratings.count(r) for r in ("STRONG", "ACCEPTABLE", "POOR")}
        return max(counts, key=counts.get)  # type: ignore[arg-type]

    @staticmethod
    def _recommend(
        m: CampaignMetrics, rating: str, missing: list[str]
    ) -> list[str]:
        """Generate rule-based recommendations from computed metrics."""
        recs: list[str] = []

        if rating == "INSUFFICIENT DATA":
            recs.append(
                "Insufficient data to make specific recommendations.  "
                "Ensure impressions, clicks, conversions, spend and revenue are recorded."
            )
            return recs

        if m.ctr_pct is not None and m.ctr_pct < _CTR_ACCEPTABLE:
            recs.append(
                "CTR is low.  Review ad creative and targeting — the audience "
                "may not find the current messaging compelling."
            )

        if m.conversion_rate_pct is not None and m.conversion_rate_pct < _CVR_ACCEPTABLE:
            recs.append(
                "Conversion rate is low.  Review the product listing, pricing and "
                "checkout experience.  Consider A/B testing product descriptions."
            )

        if m.roas is not None and m.roas < _ROAS_ACCEPTABLE:
            recs.append(
                "ROAS is below break-even threshold.  "
                "Reduce spend or improve conversion rate before scaling."
            )

        if m.roas is not None and m.roas >= _ROAS_STRONG:
            recs.append(
                "ROAS is strong.  Consider increasing budget to scale this campaign."
            )

        if m.cost_per_conversion_usd is not None and m.cost_per_conversion_usd > 0:
            recs.append(
                f"Cost per conversion is ${m.cost_per_conversion_usd:.2f}.  "
                "Compare against product margin to assess long-term viability."
            )

        if "roas" in " ".join(missing).lower() and m.spend_usd is not None:
            recs.append(
                "Revenue data is missing.  Record revenue to enable ROAS calculation."
            )

        if not recs:
            recs.append("Performance is on track.  Continue monitoring key metrics.")

        return recs
