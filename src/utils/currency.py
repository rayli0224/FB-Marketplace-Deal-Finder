"""
Currency conversion utilities for comparing Facebook Marketplace prices to eBay.

eBay prices are always in USD, so we convert Facebook Marketplace prices from other
currencies (e.g., GBP) to USD before comparison.
"""

# GBP to USD conversion rate: 1 USD = 0.73 GBP, so 1 GBP = 1/0.73 USD
GBP_TO_USD_RATE = 1 / 0.73


def convert_fb_price_to_usd(price: float, currency: str) -> float:
    """
    Convert Facebook Marketplace price to USD for eBay comparison.
    
    eBay prices are always in USD, so we convert FB GBP prices to USD.
    Returns the price unchanged if currency is not GBP.
    """
    if currency == "£":
        return price * GBP_TO_USD_RATE
    return price
