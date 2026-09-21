"""
Shared utilities used across multiple services.
Kept separate to avoid circular imports.
"""
import re

SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


def normalize_name(name: str) -> str:
    """
    Normalize a player name for cross-source matching.
    Lowercases, removes punctuation, strips name suffixes.
    Examples:
      "Ja'Marr Chase"    → "jamarr chase"
      "Calvin Ridley Jr." → "calvin ridley"
      "O'Dell Beckham"   → "odell beckham"
      "Mark Andrews II"  → "mark andrews"
      "T.J. Hockenson"   → "tj hockenson"
    """
    name = name.lower().strip()
    name = re.sub(r"['\.\-]", "", name)
    name = re.sub(r"\s+", " ", name)
    parts = [p for p in name.split() if p not in SUFFIXES]
    return " ".join(parts)


# Appended to every Gemini prompt. Em-dashes read as machine-written in the UI.
WRITING_STYLE = (
    "\n\nWriting style for all text values: plain, direct sentences like a beat "
    "reporter. Never use em-dashes or en-dashes; use commas or periods instead."
)


def strip_dashes(text: str | None) -> str | None:
    """Replace any em/en-dashes the model still emits (safe inside JSON strings)."""
    if not text:
        return text
    text = re.sub(r"(\d)\s*[—–]\s*(\d)", r"\1-\2", text)   # ranges: "1–3 weeks" -> "1-3 weeks"
    return re.sub(r"\s*[—–]\s*", ", ", text)
