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
