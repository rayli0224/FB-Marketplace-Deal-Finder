"""
Deal score calculator for comparing Facebook Marketplace prices to eBay market data.

This module calculates deal scores (percentage savings) for all listings by comparing
their prices to eBay average prices. All listings are returned with their scores,
allowing the frontend to filter and color-code based on threshold.
"""

from typing import List, Optional
from src.scrapers.fb_marketplace_scraper import Listing
from src.scrapers.ebay_scraper import PriceStats


def calculate_deal_score(fb_price: float, ebay_stats: Optional[PriceStats]) -> Optional[float]:
    """
    Calculate deal score as percentage savings compared to eBay average price.
    
    Computes how much cheaper a Facebook Marketplace listing is compared to the eBay
    average price, expressed as a percentage. For example, if eBay average is $100
    and FB price is $80, the deal score is 20% (20% savings).
    
    Args:
        fb_price: Facebook Marketplace listing price
        ebay_stats: eBay price statistics containing average price
        
    Returns:
        Deal score as percentage (e.g., 25.0 means 25% below market value).
        Returns None if eBay stats are unavailable or average price is zero.
    """
    if not ebay_stats or ebay_stats.average == 0:
        return None
    
    savings = ebay_stats.average - fb_price
    score = (savings / ebay_stats.average) * 100
    return round(score, 1)


def score_listings(
    fb_listings: List[Listing],
    ebay_stats: Optional[PriceStats],
    threshold: float
) -> List[dict]:
    """
    Score all listings with deal scores and return all results.
    
    Calculates deal scores for all Facebook Marketplace listings by comparing
    their prices to eBay market data. Returns all listings regardless of score,
    allowing the frontend to filter and color-code based on threshold.
    
    When eBay stats are unavailable or the calculation fails for a listing,
    dealScore is set to None so the frontend can distinguish "unknown" from
    a calculated score of zero.
    
    Args:
        fb_listings: List of Facebook Marketplace listings to score
        ebay_stats: eBay price statistics containing average price for comparison
        threshold: Not used for filtering (kept for API compatibility)
        
    Returns:
        List of dictionaries containing all listings with their deal scores.
        Each dictionary includes title, price, location, url, and dealScore fields.
        Deal scores are percentages (e.g., 25.0 means 25% below market value).
        dealScore is None when eBay data is unavailable or average price is zero.
    """
    scored_listings = []
    
    for listing in fb_listings:
        deal_score = calculate_deal_score(listing.price, ebay_stats)
        
        scored_listings.append({
            "title": listing.title,
            "price": listing.price,
            "location": listing.location,
            "url": listing.url,
            "dealScore": deal_score,
        })
    
    return scored_listings

