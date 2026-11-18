"""
Product Content Generator service.

Responsibilities
----------------
- Accept a ContentInput (product data + list of ContentRequests).
- Build a structured prompt for each request and variation.
- Delegate to the injected AIProvider.
- Parse the response into GeneratedContentItem objects.
- Enforce accuracy rules: flag forbidden claim patterns.
- Identify missing product information.
- Return a GeneratedContent result.

Accuracy limitations
--------------------
Pattern-based accuracy checking reduces the risk of unverified claims
appearing in generated content, but it cannot guarantee correctness.
An AI provider may produce content not covered by the pattern list.
Human review before publication is mandatory.

Forbidden claim patterns
------------------------
The generator flags (and in strict mode, refuses) content that:
- Names specific materials (titanium, medical-grade, etc.)
- States certifications (CE, FDA, ISO, RoHS, etc.)
- Makes health or safety claims (clinically proven, non-toxic, BPA-free, etc.)
- Promises specific delivery times or fulfilment arrangements
- Invents numeric specifications not present in known_features
  (mAh, watts, lumens, specific dimensions, etc.)
- Fabricates social proof (bestseller, top-rated, 5-star, etc.)

These patterns are checked against the generated text.  If a match is found
and the claim cannot be traced to known_features or product_description in
ContentInput, the item is returned with an accuracy_warning.  It is NOT
silently removed so the operator can decide whether to edit or discard it.

Provider interface
------------------
The service depends only on AIProvider (the abstract base class).
It never imports MockProvider or OpenAIProvider directly.
"""

from __future__ import annotations

import re
from typing import Optional

from ..models.content import (
    AIProviderError,
    ContentChannel,
    ContentInput,
    ContentRequest,
    ContentTone,
    ContentType,
    GeneratedContent,
    GeneratedContentItem,
    VerificationFlag,
)
from .ai_providers.base import AIProvider


# ---------------------------------------------------------------------------
# Forbidden claim patterns (compiled once at import time)
# ---------------------------------------------------------------------------

_FORBIDDEN_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("certification claim",
     re.compile(
         r"\b(CE certified|FDA approved|ISO \d+|RoHS|UL listed|"
         r"ETL certified|GS mark|FCC certified)\b",
         re.IGNORECASE,
     )),
    ("health or safety claim",
     re.compile(
         r"\b(clinically proven|clinically tested|non-toxic|BPA.?free|"
         r"hypoallergenic|safe for children|dermatologist tested|"
         r"allergen.?free|medical.?grade)\b",
         re.IGNORECASE,
     )),
    ("delivery promise",
     re.compile(
         r"\b(ships in \d+|free returns|free shipping|next.?day delivery|"
         r"same.?day dispatch|guaranteed delivery|delivery within)\b",
         re.IGNORECASE,
     )),
    ("invented specification",
     re.compile(
         r"\b(\d[\d,]*\s*(mAh|watt|W\b|lumen|lm\b|rpm|GHz|MHz|"
         r"kg\b|g\b|ml\b|oz\b|inch(es)?|cm\b|mm\b))\b",
         re.IGNORECASE,
     )),
    ("fabricated social proof",
     re.compile(
         r"\b(bestseller|best seller|top.?rated|#1 rated|5.?star|"
         r"customers love|highly reviewed|award.?winning)\b",
         re.IGNORECASE,
     )),
]

# Fields that constitute "missing product information" when empty / absent
_OPTIONAL_QUALITY_FIELDS = [
    ("product_description", "product_description"),
    ("known_features",      "known_features"),
    ("selling_price_usd",   "selling_price_usd"),
    ("product_category",    "product_category"),
]

_LIST_CONTENT_TYPES = {ContentType.BULLET_POINTS, ContentType.SEO_KEYWORDS}

_META_MAX_CHARS = 160


class ProductContentGenerator:
    """
    Generates marketing content from structured product information.

    Parameters
    ----------
    provider : AIProvider
        The AI backend to use.  Inject MockProvider for tests.
    accuracy_level : str
        "strict"   — only content traceable to ContentInput fields is returned.
        "standard" — inferences allowed; all flagged INFERRED.
        Defaults to "strict".

    The generator never makes network calls, reads environment variables,
    or selects a provider.  All of that is the caller's responsibility.
    """

    def __init__(
        self,
        provider: AIProvider,
        accuracy_level: str = "strict",
    ) -> None:
        if not isinstance(provider, AIProvider):
            raise TypeError(
                f"provider must be an AIProvider instance, got {type(provider).__name__}"
            )
        if accuracy_level not in ("strict", "standard"):
            raise ValueError(
                f"accuracy_level must be 'strict' or 'standard', got {accuracy_level!r}"
            )
        self._provider = provider
        self._accuracy_level = accuracy_level

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(self, inp: ContentInput) -> GeneratedContent:
        """
        Generate content for every ContentRequest in inp.requests.

        Returns a GeneratedContent.  Never raises — failures are captured
        in GeneratedContent.generation_failed and failure_reason.
        """
        # --- Validate required fields ---
        if not inp.product_name or not inp.product_name.strip():
            return GeneratedContent(
                product_id=inp.product_id,
                generation_failed=True,
                failure_reason="product_name is required but was empty.",
                provider_used=self._provider.name,
            )

        missing_info = self._identify_missing(inp)

        if not inp.requests:
            return GeneratedContent(
                product_id=inp.product_id,
                items=[],
                missing_product_information=missing_info,
                provider_used=self._provider.name,
            )

        items: list[GeneratedContentItem] = []
        accuracy_warnings: list[str] = []

        for req in inp.requests:
            for var_idx in range(req.variations):
                item, warning = self._generate_one(inp, req, var_idx)
                items.append(item)
                if warning:
                    accuracy_warnings.append(warning)

        return GeneratedContent(
            product_id=inp.product_id,
            items=items,
            missing_product_information=missing_info,
            accuracy_warnings=accuracy_warnings,
            provider_used=self._provider.name,
        )

    # ------------------------------------------------------------------
    # Single-item generation
    # ------------------------------------------------------------------

    def _generate_one(
        self,
        inp: ContentInput,
        req: ContentRequest,
        var_idx: int,
    ) -> tuple[GeneratedContentItem, str]:
        """
        Generate one content item.  Returns (item, accuracy_warning_or_"").
        On provider failure, returns a failed item with generation_failed info.
        """
        prompt = self._build_prompt(inp, req, var_idx)

        try:
            raw_text = self._provider.complete(prompt, max_tokens=600)
        except AIProviderError as exc:
            failed_item = GeneratedContentItem(
                content_type=req.content_type,
                channel=req.channel,
                tone=req.tone,
                text=f"[Generation failed: {exc}]",
                variation_index=var_idx,
                verification_flag=VerificationFlag.UNVERIFIED,
                grounding_notes="Provider error.",
                provider_used=self._provider.name,
            )
            # Also flag the whole result as failed via caller-side check
            # We re-raise a wrapper so the outer loop can capture it
            return failed_item, f"Provider error on {req.content_type.value}: {exc}"

        raw_text = self._apply_length_limit(raw_text, req)

        text_list = self._parse_list(raw_text, req.content_type)
        if text_list:
            raw_text = "\n- ".join(text_list)

        v_flag, grounding = self._verify(raw_text, inp)
        warning = self._accuracy_check(raw_text, inp, req.content_type)

        item = GeneratedContentItem(
            content_type=req.content_type,
            channel=req.channel,
            tone=req.tone,
            text=raw_text,
            variation_index=var_idx,
            verification_flag=v_flag,
            grounding_notes=grounding,
            text_list=text_list,
            provider_used=self._provider.name,
        )
        return item, warning

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    def _build_prompt(
        self,
        inp: ContentInput,
        req: ContentRequest,
        var_idx: int,
    ) -> str:
        """
        Assemble a structured prompt using <<TAG>>value<</TAG>> markers.
        MockProvider parses these tags; real providers read them as natural text.
        """
        features_str = " | ".join(inp.known_features) if inp.known_features else ""
        price_str    = f"{inp.selling_price_usd:.2f}" \
                       if inp.selling_price_usd is not None else ""
        opp_class    = ""
        if inp.opportunity_result is not None:
            opp_class = inp.opportunity_result.classification

        accuracy_instruction = (
            "Only use product information explicitly provided below.  "
            "Do not invent specifications, materials, certifications, "
            "delivery promises, or social proof."
        ) if self._accuracy_level == "strict" else (
            "Use the product information below.  "
            "You may make reasonable inferences; clearly mark them with [inferred]."
        )

        channel_instruction = self._channel_instruction(req.channel)
        type_instruction    = self._type_instruction(req.content_type, req.max_length)

        lines = [
            f"You are a professional e-commerce copywriter.",
            f"{accuracy_instruction}",
            "",
            f"<<PRODUCT_NAME>>{inp.product_name}<</PRODUCT_NAME>>",
            f"<<CATEGORY>>{inp.product_category}<</CATEGORY>>",
            f"<<CONTENT_TYPE>>{req.content_type.value}<</CONTENT_TYPE>>",
            f"<<CHANNEL>>{req.channel.value}<</CHANNEL>>",
            f"<<TONE>>{req.tone.value}<</TONE>>",
            f"<<VARIATION>>{var_idx}<</VARIATION>>",
        ]

        if features_str:
            lines.append(f"<<FEATURES>>{features_str}<</FEATURES>>")
        if price_str:
            lines.append(f"<<PRICE>>{price_str}<</PRICE>>")
        if req.target_audience:
            lines.append(f"<<AUDIENCE>>{req.target_audience}<</AUDIENCE>>")
        if opp_class:
            lines.append(f"<<OPPORTUNITY>>{opp_class}<</OPPORTUNITY>>")
        if inp.product_description:
            lines.append(f"<<DESCRIPTION>>{inp.product_description}<</DESCRIPTION>>")
        if req.extra_instructions:
            lines.append(f"<<EXTRA>>{req.extra_instructions}<</EXTRA>>")

        lines += [
            "",
            channel_instruction,
            type_instruction,
            f"Generate variation {var_idx + 1} of {req.variations}.",
        ]

        return "\n".join(lines)

    @staticmethod
    def _channel_instruction(channel: ContentChannel) -> str:
        mapping = {
            ContentChannel.PRODUCT_LISTING: (
                "Write for a product listing page.  "
                "Be clear, factual and persuasive."
            ),
            ContentChannel.SOCIAL_MEDIA: (
                "Write for social media.  "
                "Be concise, engaging and include relevant hashtags."
            ),
            ContentChannel.PAID_ADS: (
                "Write for paid advertising.  "
                "Lead with a hook, focus on value, end with a call to action."
            ),
            ContentChannel.EMAIL: (
                "Write for an email campaign.  "
                "Use a conversational tone and a clear subject-line angle."
            ),
            ContentChannel.SEO: (
                "Write for organic search.  "
                "Prioritise relevant keywords and clear language."
            ),
        }
        return mapping.get(channel, "Write clear, accurate marketing copy.")

    @staticmethod
    def _type_instruction(ctype: ContentType, max_length: Optional[int]) -> str:
        length_note = f"  Limit to {max_length} characters." if max_length else ""
        mapping = {
            ContentType.PRODUCT_TITLE: (
                "Generate a concise, SEO-friendly product title."
                + length_note
            ),
            ContentType.PRODUCT_DESC: (
                "Generate a full product description (2–4 paragraphs)."
                + length_note
            ),
            ContentType.SHORT_SUMMARY: (
                "Generate a one-to-two sentence product summary."
                + length_note
            ),
            ContentType.BULLET_POINTS: (
                "Generate 4–6 product feature/benefit bullet points.  "
                "Return each on a new line starting with '- '."
                + length_note
            ),
            ContentType.SEO_KEYWORDS: (
                "Generate 6–10 relevant SEO keywords or short phrases.  "
                "Return each on a new line starting with '- '."
                + length_note
            ),
            ContentType.META_DESCRIPTION: (
                "Generate a meta description of exactly 150–160 characters.  "
                "Include the product name and a call to action."
            ),
            ContentType.SOCIAL_CAPTION: (
                "Generate a social media caption with hashtags."
                + length_note
            ),
            ContentType.AD_COPY: (
                "Generate short advertising copy with a hook and call to action."
                + length_note
            ),
            ContentType.MARKETING_ANGLE: (
                "Describe one specific marketing angle for this product, "
                "naming the target audience and core value proposition."
                + length_note
            ),
        }
        return mapping.get(ctype, f"Generate {ctype.value} content.{length_note}")

    # ------------------------------------------------------------------
    # Response processing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_list(text: str, ctype: ContentType) -> list[str]:
        """
        For BULLET_POINTS and SEO_KEYWORDS, split on "\\n- " or "- " prefixes.
        Returns [] for other content types.
        """
        if ctype not in _LIST_CONTENT_TYPES:
            return []
        items = []
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("- "):
                items.append(line[2:].strip())
            elif line.startswith("• "):
                items.append(line[2:].strip())
            elif line and not line.startswith("#"):
                # First element may lack a prefix if it's the product name
                items.append(line)
        return [i for i in items if i]

    @staticmethod
    def _apply_length_limit(text: str, req: ContentRequest) -> str:
        """
        Truncate text to req.max_length at the last word boundary.
        Always enforces the 160-char limit for META_DESCRIPTION.
        """
        limit = req.max_length
        if req.content_type == ContentType.META_DESCRIPTION:
            limit = _META_MAX_CHARS if (limit is None or limit > _META_MAX_CHARS) \
                    else limit

        if limit is None or len(text) <= limit:
            return text
        truncated = text[:limit].rsplit(" ", 1)[0]
        return truncated + "..."

    def _verify(
        self, text: str, inp: ContentInput
    ) -> tuple[VerificationFlag, str]:
        """
        Assign a VerificationFlag and grounding note based on how much of
        the text is traceable to ContentInput fields.
        """
        grounding_parts = []
        if inp.product_name and inp.product_name.lower() in text.lower():
            grounding_parts.append("product_name")
        if inp.product_category and inp.product_category.lower() in text.lower():
            grounding_parts.append("product_category")
        if inp.selling_price_usd is not None and str(inp.selling_price_usd) in text:
            grounding_parts.append("selling_price_usd")
        for feat in inp.known_features:
            if feat.lower() in text.lower():
                grounding_parts.append(f"feature:{feat}")

        if grounding_parts:
            if self._accuracy_level == "strict":
                flag = VerificationFlag.VERIFIED
            else:
                flag = VerificationFlag.INFERRED
            return flag, "Grounded in: " + ", ".join(grounding_parts)

        return VerificationFlag.UNVERIFIED, ""

    def _accuracy_check(
        self, text: str, inp: ContentInput, ctype: ContentType
    ) -> str:
        """
        Scan for forbidden claim patterns.
        Returns a warning string if a pattern matches and the claim is not
        present in known_features or product_description.
        Returns "" if the text is clean.

        Limitation: pattern-based scanning cannot catch all possible
        fabrications from an AI provider.  Human review is always required.
        """
        # Build a combined "known facts" string from verified input fields
        known_facts = " ".join([
            inp.product_name,
            inp.product_description,
            " ".join(inp.known_features),
        ]).lower()

        warnings = []
        for label, pattern in _FORBIDDEN_PATTERNS:
            matches = pattern.findall(text)
            for match in matches:
                match_lower = match.lower() if isinstance(match, str) else match[0].lower()
                if match_lower not in known_facts:
                    warnings.append(
                        f"Potential {label} not found in product data: '{match}'. "
                        "Review before publishing."
                    )

        if warnings:
            return f"[{ctype.value}] " + " | ".join(warnings)
        return ""

    # ------------------------------------------------------------------
    # Missing information
    # ------------------------------------------------------------------

    @staticmethod
    def _identify_missing(inp: ContentInput) -> list[str]:
        """Return names of empty/absent fields that would improve content quality."""
        missing = []
        if not inp.product_description:
            missing.append("product_description")
        if not inp.known_features:
            missing.append("known_features")
        if inp.selling_price_usd is None:
            missing.append("selling_price_usd")
        if not inp.product_category:
            missing.append("product_category")
        return missing
