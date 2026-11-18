"""
MockProvider — deterministic AI provider for testing and development.

Design goals
------------
- Requires no API key and makes no network calls.
- Returns repeatable, template-filled output based on the prompt.
- Produces meaningfully different output for each variation index so that
  "each variation has distinct text" tests pass reliably.
- Supports a configurable failure mode for testing error-handling paths.
- Never fabricates product specifications, materials or certifications.

Prompt parsing
--------------
The mock provider reads structured tags that ProductContentGenerator
embeds in every prompt:

    <<PRODUCT_NAME>>Rechargeable LED Lantern<</PRODUCT_NAME>>
    <<CATEGORY>>Home & Outdoors<</CATEGORY>>
    <<CONTENT_TYPE>>PRODUCT_TITLE<</CONTENT_TYPE>>
    <<CHANNEL>>PRODUCT_LISTING<</CHANNEL>>
    <<TONE>>PROFESSIONAL<</TONE>>
    <<VARIATION>>0<</VARIATION>>
    <<FEATURES>>feature 1 | feature 2<</FEATURES>>
    <<PRICE>>22.00<</PRICE>>
    <<AUDIENCE>>outdoor enthusiasts<</AUDIENCE>>
    <<OPPORTUNITY>>STRONG<</OPPORTUNITY>>

Unknown tags are ignored.  Missing tags fall back to safe defaults.
"""

from __future__ import annotations

import re
from typing import Optional

from ...models.content import AIProviderError
from .base import AIProvider


# Variation modifiers applied to titles, summaries, etc.
_VARIATION_ADJECTIVES = [
    "Quality",
    "Premium",
    "Reliable",
    "Trusted",
    "Everyday",
]

_VARIATION_OPENERS = [
    "Discover the",
    "Introducing the",
    "Experience the",
    "Shop the",
    "Find your",
]

_VARIATION_ANGLES = [
    "Perfect for everyday use.",
    "Designed to meet your needs.",
    "Built for performance and value.",
    "A smart choice for savvy shoppers.",
    "Great quality at a fair price.",
]

_AD_HOOKS = [
    "Ready to upgrade?",
    "Don't settle for less.",
    "Make the smart choice today.",
    "Value you can trust.",
    "Quality without compromise.",
]

_SOCIAL_OPENERS = [
    "✨ Just in:",
    "🛒 New arrival:",
    "🌟 Check this out:",
    "🔥 Hot product:",
    "💡 Did you know?",
]


def _extract(tag: str, prompt: str) -> str:
    """Extract the value between <<TAG>> and <</TAG>>. Returns '' if absent."""
    m = re.search(rf"<<{tag}>>(.*?)<</{ tag}>>", prompt, re.DOTALL)
    return m.group(1).strip() if m else ""


class MockProvider(AIProvider):
    """
    Deterministic provider for unit tests and offline development.

    Parameters
    ----------
    force_failure : bool
        When True, complete() always raises AIProviderError.
        Use this to test the generator's error-handling path.
    failure_message : str
        The message in the raised AIProviderError when force_failure=True.
    """

    def __init__(
        self,
        force_failure: bool = False,
        failure_message: str = "MockProvider: simulated failure.",
    ) -> None:
        self._force_failure = force_failure
        self._failure_message = failure_message

    @property
    def name(self) -> str:
        return "mock"

    def complete(self, prompt: str, max_tokens: int = 500) -> str:
        if self._force_failure:
            raise AIProviderError(self._failure_message)

        name     = _extract("PRODUCT_NAME", prompt) or "this product"
        category = _extract("CATEGORY",     prompt) or "General"
        ctype    = _extract("CONTENT_TYPE", prompt) or "PRODUCT_TITLE"
        tone     = _extract("TONE",         prompt) or "PROFESSIONAL"
        channel  = _extract("CHANNEL",      prompt) or "PRODUCT_LISTING"
        audience = _extract("AUDIENCE",     prompt) or "general shoppers"
        price    = _extract("PRICE",        prompt)
        opp      = _extract("OPPORTUNITY",  prompt)  # STRONG / MODERATE / WEAK / POOR / ""

        # Variation index — drives meaningful differences between alternatives
        var_raw  = _extract("VARIATION",    prompt)
        try:
            var = int(var_raw)
        except ValueError:
            var = 0
        idx = var % len(_VARIATION_ADJECTIVES)

        adj     = _VARIATION_ADJECTIVES[idx]
        opener  = _VARIATION_OPENERS[idx]
        angle   = _VARIATION_ANGLES[idx]
        hook    = _AD_HOOKS[idx]
        s_open  = _SOCIAL_OPENERS[idx]

        price_str = f"${price}" if price else "competitively priced"

        # Features list (pipe-separated in prompt)
        features_raw = _extract("FEATURES", prompt)
        features = [f.strip() for f in features_raw.split("|") if f.strip()] \
                   if features_raw else []

        # Opportunity-aware emphasis
        opp_note = ""
        if opp == "STRONG":
            opp_note = "High-demand product with strong market opportunity."
        elif opp == "MODERATE":
            opp_note = "Solid market opportunity."
        elif opp in ("WEAK", "POOR"):
            opp_note = "Niche product — targeted appeal."

        # --- Dispatch by content type ---
        if ctype == "PRODUCT_TITLE":
            return self._title(name, category, adj, opp_note)

        if ctype == "PRODUCT_DESC":
            return self._description(name, category, adj, features, price_str,
                                     opp_note, angle, tone)

        if ctype == "SHORT_SUMMARY":
            return self._summary(name, category, opener, angle, opp_note)

        if ctype == "BULLET_POINTS":
            return self._bullets(name, category, features, price_str, idx)

        if ctype == "SEO_KEYWORDS":
            return self._keywords(name, category, idx)

        if ctype == "META_DESCRIPTION":
            return self._meta(name, category, adj, price_str, opp_note)

        if ctype == "SOCIAL_CAPTION":
            return self._social(name, category, s_open, price_str,
                                channel, opp_note, idx)

        if ctype == "AD_COPY":
            return self._ad_copy(name, category, hook, price_str,
                                 audience, opp_note, idx)

        if ctype == "MARKETING_ANGLE":
            return self._marketing_angle(name, category, audience,
                                         adj, opp_note, idx)

        # Fallback for unknown types
        return f"{adj} {name} — {category}. Variation {var}."

    # ------------------------------------------------------------------
    # Content type helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _title(name: str, category: str, adj: str, opp: str) -> str:
        opp_part = f" | {opp}" if opp else ""
        return f"{adj} {name} — {category}{opp_part}"

    @staticmethod
    def _description(
        name: str, category: str, adj: str,
        features: list, price_str: str,
        opp: str, angle: str, tone: str,
    ) -> str:
        feature_lines = ""
        if features:
            feature_lines = " Features include: " + "; ".join(features) + "."
        opp_line = f" {opp}" if opp else ""
        tone_note = " Written for a professional audience." \
                    if tone == "PROFESSIONAL" else ""
        return (
            f"{adj} {name} is a {category.lower()} product {price_str}."
            f"{feature_lines}{opp_line} {angle}{tone_note}"
        ).strip()

    @staticmethod
    def _summary(
        name: str, category: str,
        opener: str, angle: str, opp: str,
    ) -> str:
        opp_part = f" {opp}" if opp else ""
        return f"{opener} {name}, a {category.lower()} product.{opp_part} {angle}"

    @staticmethod
    def _bullets(
        name: str, category: str,
        features: list, price_str: str, idx: int,
    ) -> str:
        base = [
            f"{name}",
            f"Category: {category}",
            f"Price: {price_str}",
        ]
        # Add any known features, capped at 5
        for f in features[:5]:
            base.append(f)
        # Variation-driven extra bullet
        extras = [
            "Ideal for everyday use",
            "Carefully selected for quality",
            "Ships from verified suppliers",
            "Suitable for a wide range of users",
            "Competitive pricing on the market",
        ]
        base.append(extras[idx % len(extras)])
        return "\n- ".join(base)

    @staticmethod
    def _keywords(name: str, category: str, idx: int) -> str:
        base = [
            name,
            f"buy {name}",
            f"{name} online",
            category,
            f"{category} products",
            f"best {name}",
        ]
        extras = [
            [f"affordable {name}", f"{name} deal"],
            [f"top {name}", f"{name} review"],
            [f"{name} for sale", f"cheap {name}"],
            [f"quality {name}", f"{name} price"],
            [f"{name} shop", f"order {name}"],
        ]
        base.extend(extras[idx % len(extras)])
        return "\n- ".join(base)

    @staticmethod
    def _meta(
        name: str, category: str, adj: str,
        price_str: str, opp: str,
    ) -> str:
        opp_part = f" {opp}" if opp else ""
        raw = (
            f"Shop {adj} {name} in {category}. "
            f"Available {price_str}.{opp_part} "
            f"Browse our selection today."
        )
        # Enforce 160-char meta limit
        if len(raw) > 160:
            raw = raw[:157].rsplit(" ", 1)[0] + "..."
        return raw

    @staticmethod
    def _social(
        name: str, category: str, opener: str,
        price_str: str, channel: str, opp: str, idx: int,
    ) -> str:
        hashtags = [
            f"#{name.replace(' ', '')} #{category.replace(' ', '')} #OnlineShopping",
            f"#{category.replace(' ', '')} #NewArrivals #ShopNow",
            f"#{name.replace(' ', '')} #Deal #Ecommerce",
            f"#Shopping #{category.replace(' ', '')} #Quality",
            f"#{name.replace(' ', '')} #BestPrice #Trending",
        ]
        opp_part = f" {opp}" if opp else ""
        tag = hashtags[idx % len(hashtags)]
        return (
            f"{opener} {name} — now available {price_str}.{opp_part}\n{tag}"
        )

    @staticmethod
    def _ad_copy(
        name: str, category: str, hook: str,
        price_str: str, audience: str, opp: str, idx: int,
    ) -> str:
        ctas = [
            "Shop now.",
            "Order today.",
            "Get yours.",
            "Buy now.",
            "Limited availability.",
        ]
        opp_part = f" {opp}" if opp else ""
        cta = ctas[idx % len(ctas)]
        return (
            f"{hook} {name} — {category} for {audience}.{opp_part} "
            f"Available {price_str}. {cta}"
        )

    @staticmethod
    def _marketing_angle(
        name: str, category: str, audience: str,
        adj: str, opp: str, idx: int,
    ) -> str:
        angles = [
            f"Value angle: Position {name} as the affordable choice for {audience} in {category}.",
            f"Quality angle: Emphasise {adj.lower()} quality for {audience}.",
            f"Convenience angle: Highlight ease of ordering for {audience}.",
            f"Discovery angle: Introduce {name} to {audience} as a new find.",
            f"Comparison angle: Show why {name} stands out in {category} for {audience}.",
        ]
        opp_part = f" Opportunity: {opp}." if opp else ""
        return angles[idx % len(angles)] + opp_part
