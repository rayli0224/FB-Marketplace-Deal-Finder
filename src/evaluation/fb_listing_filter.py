"""
Mechanical filter for Facebook Marketplace listings with suspicious or fake prices.

Filters out listings where the displayed price is likely not the real price:
free items, $1 items, and items above $100 that are not a multiple of 5.
"""

SUSPICIOUS_FREE = 0.0
SUSPICIOUS_ONE_DOLLAR = 1.0
SUSPICIOUS_HIGH_THRESHOLD = 100.0


def is_suspicious_price(price: float) -> bool:
    """
    Return True if the price indicates a likely fake or placeholder listing.

    Filters: free ($0), $1 items, and prices above $100 that are not a multiple of 5.
    Uses rounded dollar amount for the multiple-of-5 check to handle floating point.
    """
    if price <= SUSPICIOUS_FREE:
        return True
    if price == SUSPICIOUS_ONE_DOLLAR:
        return True
    if price > SUSPICIOUS_HIGH_THRESHOLD:
        rounded = round(price)
        return rounded % 5 != 0
    return False
