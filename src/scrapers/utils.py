"""
Shared utility functions for scrapers.
"""

import re
import time
import random
from typing import Optional


def random_delay(min_sec: float = 1.0, max_sec: float = 3.0):
    """Add a random delay to mimic human behavior."""
    delay = random.uniform(min_sec, max_sec)
    time.sleep(delay)


# Placeholder values that are not real listing prices (e.g. post IDs like 123, 1234).
# Excludes 1 so real $1 sale prices (e.g. strikethrough) are kept.
_INVALID_PRICES = (123, 1234, 12345, 123456, 1234567, 12345678, 123456789)


def parse_price(price_text: str) -> Optional[float]:
    """
    Parse a price string into a float.

    Handles $123.45, $1,234.56, "Free", and "CA$20". When both original and sale price
    appear (e.g., "$50 $15" or "$50 FREE"), returns the sale price (lowest value).
    When 3+ numbers exist (e.g. "1 available"), filters placeholder values before min.
    """
    try:
        text = price_text.strip()
        if not text:
            return None

        if text.lower() == "free":
            return 0.0

        numbers = re.findall(r"[\d.]+", text.replace(",", ""))
        candidates: list[float] = []
        for n in numbers:
            v = float(n)
            if v >= 0:
                candidates.append(v)
        if re.search(r"\bfree\b", text, re.IGNORECASE):
            candidates.append(0.0)
        if len(candidates) >= 3:
            valid = [c for c in candidates if c not in _INVALID_PRICES]
        else:
            valid = candidates
        if not valid:
            return None
        return min(valid)
    except (ValueError, AttributeError):
        return None


def is_valid_listing_price(price: Optional[float]) -> bool:
    """Check if a listing price is valid (not a placeholder like $123, post IDs, etc.)."""
    if price is None:
        return False
    return price not in _INVALID_PRICES

