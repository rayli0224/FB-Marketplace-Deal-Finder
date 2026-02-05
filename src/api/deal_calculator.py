"""
Deal score calculator for comparing Facebook Marketplace prices to eBay market data.
"""

from typing import List, Optional
from src.scrapers.fb_marketplace_scraper import Listing
from src.scrapers.ebay_scraper import PriceStats


def calculate_deal_score(fb_price: float, ebay_stats: Optional[PriceStats]) -> Optional[float]:
    """
    Calculate deal score as percentage savings compared to eBay average price.
    
    Returns:
        Deal score as percentage (e.g., 25.0 means 25% below market value)
        None if eBay stats are not available
    """
    if not ebay_stats or ebay_stats.average == 0:
        return None
    
    savings = ebay_stats.average - fb_price
    score = (savings / ebay_stats.average) * 100
    return round(score, 1)


def filter_and_score_listings(
    fb_listings: List[Listing],
    ebay_stats: Optional[PriceStats],
    threshold: float = 20.0
) -> List[dict]:
    """
    Filter listings by deal score threshold and return scored results.
    
    Args:
        fb_listings: List of Facebook Marketplace listings
        ebay_stats: eBay price statistics for comparison
        threshold: Minimum deal score percentage to include
        
    Returns:
        List of dictionaries with listing data and deal scores
    """
    scored_listings = []
    
    for listing in fb_listings:
        deal_score = calculate_deal_score(listing.price, ebay_stats)
        
        if deal_score is not None and deal_score >= threshold:
            scored_listings.append({
                "title": listing.title,
                "price": listing.price,
                "location": listing.location,
                "url": listing.url,
                "dealScore": deal_score,
            })
    
    return scored_listings

