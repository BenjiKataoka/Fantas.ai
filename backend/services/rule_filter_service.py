"""
Rule-based pre-filter applied to ALL news items before Gemini.

For rostered-only players: writes result directly → no Gemini ever.
For starred players: if a rule matches → write result directly (skip Gemini).
                     if no rule matches → proceed to Gemini Pass 1.

During offseason (season_type="off"): Gemini is gated to significant events only.
Routine noise always resolves to NEUTRAL/LOW with no Gemini call.
"""

import re
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# Keywords that map to a stock direction + magnitude + confidence without Gemini
# Rules are evaluated in order — first match wins.
RULES = [
    # BEARISH HIGH — playing status / serious injury
    {
        "patterns": [
            r"\bruled out\b",
            r"\bplaced on IR\b",
            r"\bseason[- ]ending\b",
            r"\bsurgery\b",
            r"\btorn\b",
            r"\bfracture[d]?\b",
            r"\bACL\b",
            r"\bamenity surgery\b",  # keep typo-safe via fuzzy list
        ],
        "direction": "BEARISH",
        "magnitude": "HIGH",
        "confidence": 0.95,
        "news_type_hint": "INJURY",
        "offseason_significant": True,
    },
    # BEARISH MEDIUM — soft injury / game-time doubt
    {
        "patterns": [
            r"\bdoubtful\b",
            r"\bwon't play\b",
            r"\bwill not play\b",
            r"\bmissed practice\b",
            r"\bmissed (?:Wednesday|Thursday|Friday) practice\b",
            r"\bsprained\b",
            r"\bstrained\b",
            r"\bhamstring\b",
            r"\bcut by\b",
            r"\breleased by\b",
        ],
        "direction": "BEARISH",
        "magnitude": "MEDIUM",
        "confidence": 0.80,
        "news_type_hint": "INJURY",
        "offseason_significant": False,
    },
    # BEARISH MEDIUM — roster / depth chart demotion
    {
        "patterns": [
            r"\bdemoted\b",
            r"\bdropped to second[- ]string\b",
            r"\blost.*starting job\b",
            r"\bbench[ed]?\b.*starter",
            r"\btrade[d]? to\b",
            r"\btraded to\b",
        ],
        "direction": "BEARISH",
        "magnitude": "MEDIUM",
        "confidence": 0.82,
        "news_type_hint": "DEPTH_CHART",
        "offseason_significant": True,
    },
    # BULLISH HIGH — return from injury / contract extension
    {
        "patterns": [
            r"\bactivated from IR\b",
            r"\bcleared to return\b",
            r"\bsigned.*extension\b",
            r"\bextension.*signed\b",
            r"\bfull practice\b",
            r"\bfull participant\b",
            r"\bno injury designation\b",
            r"\bexpected to play\b",
        ],
        "direction": "BULLISH",
        "magnitude": "HIGH",
        "confidence": 0.88,
        "news_type_hint": "INJURY",
        "offseason_significant": True,
    },
    # BULLISH MEDIUM — depth chart promotion / signing
    {
        "patterns": [
            r"\bnamed.*starter\b",
            r"\bpromoted\b",
            r"\bsigned.*deal\b",
            r"\bsigned a.*contract\b",
            r"\bwill start\b",
            r"\bexpected to be.*starter\b",
        ],
        "direction": "BULLISH",
        "magnitude": "MEDIUM",
        "confidence": 0.82,
        "news_type_hint": "DEPTH_CHART",
        "offseason_significant": True,
    },
    # NEUTRAL LOW — routine noise
    {
        "patterns": [
            r"\blimited practice\b",
            r"\blimited participant\b",
            r"\bveteran day off\b",
            r"\brest day\b",
            r"\bmanagement day\b",
            r"\blooks good in OTAs?\b",
            r"\bOTA[s]? workout\b",
            r"\bminicamp\b",
        ],
        "direction": "NEUTRAL",
        "magnitude": "LOW",
        "confidence": 0.70,
        "news_type_hint": "GENERAL",
        "offseason_significant": False,
    },
]

# News types that are always significant even in the offseason
OFFSEASON_SIGNIFICANT_TYPES = {"INJURY", "TRANSACTION", "CONTRACT", "DEPTH_CHART"}

# Keywords that indicate a news item is offseason-significant even if no rule matched
OFFSEASON_KEYWORDS = [
    r"\binjur",
    r"\btrade[d]?\b",
    r"\bsign(ed|ing)?\b",
    r"\bcontract\b",
    r"\bdepth chart\b",
    r"\bcut\b",
    r"\breleased?\b",
    r"\bretire[sd]?\b",
    r"\bsuspend",
]


@dataclass
class FilterResult:
    matched: bool                        # True = rule fired; False = pass to Gemini
    direction: Optional[str] = None      # BULLISH / BEARISH / NEUTRAL
    magnitude: Optional[str] = None      # HIGH / MEDIUM / LOW
    confidence: Optional[float] = None
    news_type_hint: Optional[str] = None
    offseason_significant: bool = False  # Whether to run Gemini in offseason


def apply_rule_filter(
    headline: str,
    news_body: Optional[str],
    season_type: str,
) -> FilterResult:
    """
    Apply keyword rules to a news item.

    season_type: "off" | "pre" | "regular" | "post"

    Returns FilterResult.matched=True if a rule fired (skip or gate Gemini).
    Returns FilterResult.matched=False if no rule matched (proceed to Gemini for starred).
    """
    text = f"{headline} {news_body or ''}".lower()

    for rule in RULES:
        for pattern in rule["patterns"]:
            if re.search(pattern, text, re.IGNORECASE):
                result = FilterResult(
                    matched=True,
                    direction=rule["direction"],
                    magnitude=rule["magnitude"],
                    confidence=rule["confidence"],
                    news_type_hint=rule["news_type_hint"],
                    offseason_significant=rule["offseason_significant"],
                )
                logger.debug(
                    f"[RuleFilter] matched pattern '{pattern}' → "
                    f"{result.direction}/{result.magnitude} ({result.confidence})"
                )
                return result

    # No rule matched — check if this item is offseason-significant for the gate decision
    is_offseason_significant = _is_offseason_significant(text)

    return FilterResult(
        matched=False,
        offseason_significant=is_offseason_significant,
    )


def should_run_gemini(
    filter_result: FilterResult,
    is_starred: bool,
    season_type: str,
) -> bool:
    """
    Decide whether to enqueue this item for Gemini analysis.

    Rules:
    - Rostered-only (not starred) → never Gemini
    - Rule matched for starred → no Gemini (rule result is sufficient)
    - No rule match + starred + in-season → Gemini
    - No rule match + starred + offseason → Gemini only if offseason_significant
    """
    if not is_starred:
        return False

    if filter_result.matched:
        # Rule already has a confident answer — Gemini not needed
        return False

    if season_type == "off":
        # Offseason: only analyze significant events
        return filter_result.offseason_significant

    # Pre/regular/post season: run Gemini for all unmatched starred items
    return True


def _is_offseason_significant(text: str) -> bool:
    """Returns True if text contains at least one offseason-significant keyword."""
    for pattern in OFFSEASON_KEYWORDS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False
