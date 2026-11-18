"""
Content generation models for the AI Dropshipping Agent.

Four layers
-----------
ContentRequest      What to generate: type, channel, tone, variations.
ContentInput        Full context passed to ProductContentGenerator.
GeneratedContentItem  One piece of generated content with provenance.
GeneratedContent    Full output of a single generate() call.

Design rules
------------
- None always means "not set / not available".
- text_list is populated for BULLET_POINTS and SEO_KEYWORDS; text holds the
  same data joined by "\\n- " for backward compatibility.
- VerificationFlag must never be set to VERIFIED unless the claim is
  traceable to an explicit field in ContentInput.
- Generated content must be reviewed by a human before publication.
  No field in these models implies publication readiness.
- No purchasing, payment, inventory, fulfilment or dispatch fields.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .opportunity import OpportunityResult


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ContentChannel(str, Enum):
    """The marketing channel this content is intended for."""
    PRODUCT_LISTING  = "PRODUCT_LISTING"
    SOCIAL_MEDIA     = "SOCIAL_MEDIA"
    PAID_ADS         = "PAID_ADS"
    EMAIL            = "EMAIL"
    SEO              = "SEO"


class ContentType(str, Enum):
    """The specific piece of content being generated."""
    PRODUCT_TITLE    = "PRODUCT_TITLE"
    PRODUCT_DESC     = "PRODUCT_DESC"
    SHORT_SUMMARY    = "SHORT_SUMMARY"
    BULLET_POINTS    = "BULLET_POINTS"
    SEO_KEYWORDS     = "SEO_KEYWORDS"
    META_DESCRIPTION = "META_DESCRIPTION"
    SOCIAL_CAPTION   = "SOCIAL_CAPTION"
    AD_COPY          = "AD_COPY"
    MARKETING_ANGLE  = "MARKETING_ANGLE"


class ContentTone(str, Enum):
    """Tone of voice for the generated content."""
    PROFESSIONAL  = "PROFESSIONAL"
    CASUAL        = "CASUAL"
    ENTHUSIASTIC  = "ENTHUSIASTIC"
    MINIMALIST    = "MINIMALIST"


class VerificationFlag(str, Enum):
    """
    Confidence that a content claim is grounded in real input data.

    VERIFIED    — claim is directly traceable to a field in ContentInput.
    INFERRED    — reasonably derived but not an explicit data field.
    UNVERIFIED  — could not be confirmed from the provided data.

    Important: VERIFIED does not mean the underlying product data has been
    confirmed with the supplier or manufacturer.  It only means the claim
    matches what the operator supplied.  Human review is always required
    before publication.
    """
    VERIFIED   = "VERIFIED"
    INFERRED   = "INFERRED"
    UNVERIFIED = "UNVERIFIED"


# ---------------------------------------------------------------------------
# Error type
# ---------------------------------------------------------------------------

class AIProviderError(Exception):
    """
    Raised by an AIProvider when it cannot complete the request.
    Covers network failures, authentication errors, timeouts, and
    malformed or empty responses.
    """


# ---------------------------------------------------------------------------
# ContentRequest
# ---------------------------------------------------------------------------

@dataclass
class ContentRequest:
    """
    A single content generation request.

    variations must be between 1 and 5 inclusive.
    extra_instructions may add context but must NOT override accuracy rules
    or instruct the generator to invent specifications or certifications.
    """
    content_type: ContentType
    channel: ContentChannel
    tone: ContentTone = ContentTone.PROFESSIONAL
    max_length: Optional[int] = None   # chars; None = provider default
    variations: int = 1
    target_audience: str = ""
    extra_instructions: str = ""

    def __post_init__(self) -> None:
        if not (1 <= self.variations <= 5):
            raise ValueError(
                f"variations must be between 1 and 5, got {self.variations}"
            )
        if self.max_length is not None and self.max_length <= 0:
            raise ValueError(
                f"max_length must be > 0, got {self.max_length}"
            )


# ---------------------------------------------------------------------------
# ContentInput
# ---------------------------------------------------------------------------

@dataclass
class ContentInput:
    """
    Full context passed to ProductContentGenerator.generate().

    Fields
    ------
    product_id          : Matches Product.id.
    product_name        : Required.  The generator cannot produce usable
                          content without at least a product name.
    product_category    : Optional but improves relevance.
    product_description : Operator-supplied description; may be empty.
    known_features      : Confirmed product features.  The generator will
                          only reference these — it will not invent features.
    selling_price_usd   : Optional.  Absence is flagged in output.
    opportunity_result  : Optional OpportunityResult from Step 5.
                          Used to adapt tone and emphasis.
    requests            : What to generate.  Empty list returns empty items.
    data_verified       : True only if the operator has confirmed the product
                          information against a live source.
    """
    product_id: str
    product_name: str = ""
    product_category: str = ""
    product_description: str = ""
    known_features: list = field(default_factory=list)
    selling_price_usd: Optional[float] = None
    opportunity_result: Optional[OpportunityResult] = None
    requests: list = field(default_factory=list)   # list[ContentRequest]
    data_verified: bool = False


# ---------------------------------------------------------------------------
# GeneratedContentItem
# ---------------------------------------------------------------------------

@dataclass
class GeneratedContentItem:
    """
    One piece of generated content.

    text          : The generated string.  For BULLET_POINTS and SEO_KEYWORDS
                    this contains items joined by "\\n- " for display convenience.
    text_list     : Populated for BULLET_POINTS and SEO_KEYWORDS; each element
                    is one bullet point or keyword.  Empty list for other types.
    char_count    : Set automatically to len(text) on creation.
    provider_used : Which AIProvider produced this item.

    Accuracy note
    -------------
    verification_flag reflects how well the content is grounded in ContentInput.
    VERIFIED does not mean the product data itself has been validated with the
    supplier.  Human review before publication is mandatory.
    """
    content_type: ContentType
    channel: ContentChannel
    tone: ContentTone
    text: str
    variation_index: int = 0
    verification_flag: VerificationFlag = VerificationFlag.UNVERIFIED
    grounding_notes: str = ""
    text_list: list = field(default_factory=list)   # list[str]
    char_count: int = 0
    provider_used: str = ""

    def __post_init__(self) -> None:
        self.char_count = len(self.text)


# ---------------------------------------------------------------------------
# GeneratedContent
# ---------------------------------------------------------------------------

@dataclass
class GeneratedContent:
    """
    Full output of one ProductContentGenerator.generate() call.

    items                      : All generated items across all requests.
    missing_product_information: Fields absent from ContentInput that would
                                 improve content quality.
    accuracy_warnings          : Claims in the output that could not be
                                 verified against ContentInput.
    provider_used              : Name of the AIProvider used.
    generation_failed          : True if the provider could not complete the
                                 request.  items may be empty.
    failure_reason             : Human-readable explanation if generation_failed.

    Important: this output requires human review before any item is published.
    """
    product_id: str
    items: list = field(default_factory=list)         # list[GeneratedContentItem]
    missing_product_information: list = field(default_factory=list)   # list[str]
    accuracy_warnings: list = field(default_factory=list)             # list[str]
    provider_used: str = ""
    generation_failed: bool = False
    failure_reason: str = ""
