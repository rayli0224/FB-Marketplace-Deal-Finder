"""
Deal score calculator for comparing Facebook Marketplace prices to eBay market data.

This module calculates deal scores (percentage savings) for all listings by comparing
their prices to eBay average prices. All listings are returned with their scores,
allowing the frontend to filter and color-code based on threshold.
"""

from typing import List, Optional
from src.scrapers.fb_marketplace_scraper import Listing
from src.scrapers.ebay_scraper_v2 import PriceStats

# GBP to USD conversion rate: 1 USD = 0.73 GBP, so 1 GBP = 1/0.73 USD
GBP_TO_USD_RATE = 1 / 0.73


def _convert_fb_price_to_usd(price: float, currency: str) -> float:
    """
    Convert Facebook Marketplace price to USD for eBay comparison.
    eBay prices are always in USD, so we convert FB GBP prices to USD.
    Returns the price unchanged if currency is not GBP.
    """
    if currency == "£":
        return price * GBP_TO_USD_RATE
    return price


def calculate_deal_score(fb_price: float, ebay_stats: Optional[PriceStats]) -> Optional[float]:
    """
    Calculate deal score as percentage savings vs eBay average. E.g. if eBay avg
    is $100 and FB price is $80, score is 20% savings. Returns None if eBay stats
    unavailable or average price is zero.
    """
    if not ebay_stats or ebay_stats.average == 0:
        return None

    savings = ebay_stats.average - fb_price
    score = (savings / ebay_stats.average) * 100
    return round(score, 1)


def score_listings(
    fb_listings: List[Listing],
    ebay_stats: Optional[PriceStats],
) -> List[dict]:
    """
    Score all FB listings by comparing prices to eBay market data. Returns all
    listings with deal scores; frontend filters/color-codes by threshold.
    dealScore is None when eBay stats unavailable or average price is zero.
    """
    scored_listings = []

    for listing in fb_listings:
        # Convert FB price to USD for comparison (eBay prices are always in USD)
        fb_price_usd = _convert_fb_price_to_usd(listing.price, listing.currency)
        deal_score = calculate_deal_score(fb_price_usd, ebay_stats)

        scored_listings.append({
            "title": listing.title,
            "price": listing.price,
            "currency": listing.currency,
            "location": listing.location,
            "url": listing.url,
            "dealScore": deal_score,
        })

    return scored_listings
