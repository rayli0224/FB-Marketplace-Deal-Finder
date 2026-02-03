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


def parse_price(price_text: str) -> Optional[float]:
    """Parse a price string into a float. Handles formats like $123.45, $1,234.56, or 'Free'."""
    try:
        price_text = price_text.strip().replace("$", "").replace(",", "")
        
        if price_text.lower() == "free":
            return None
        
        match = re.search(r'[\d.]+', price_text)
        if match:
            price = float(match.group())
            return price if price > 0 else None
        
        return None
    except (ValueError, AttributeError):
        return None


def is_valid_listing_price(price: Optional[float]) -> bool:
    """Check if a listing price is valid (not a placeholder like $1, $123, etc.)."""
    if price is None:
        return False
    
    invalid_prices = [1, 123, 1234, 12345, 123456, 1234567, 12345678, 123456789]
    return price not in invalid_prices

