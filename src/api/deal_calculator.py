"""
Deal score calculator for comparing Facebook Marketplace prices to eBay market data.

This module calculates deal scores (percentage savings) and filters listings based on
a threshold expressed as a percentage of eBay average price.
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


def _calculate_max_price_for_threshold(ebay_average: float, threshold_percentage: float) -> float:
    """
    Calculate the maximum price allowed for a given threshold percentage.
    
    Converts a threshold percentage (e.g., 80.0) into an absolute price value.
    For example, if eBay average is $100 and threshold is 80%, returns $80.
    
    Args:
        ebay_average: Average eBay price for comparison
        threshold_percentage: Threshold as percentage of eBay average (0-100)
        
    Returns:
        Maximum price allowed to meet the threshold
    """
    return (threshold_percentage / 100.0) * ebay_average


def _listing_meets_price_threshold(listing: Listing, max_price: float) -> bool:
    """
    Check if a listing's price meets the maximum price threshold.
    
    Args:
        listing: Facebook Marketplace listing to check
        max_price: Maximum allowed price
        
    Returns:
        True if listing price is less than or equal to max_price, False otherwise
    """
    return listing.price <= max_price


def _convert_listing_to_scored_dict(listing: Listing, deal_score: float) -> dict:
    """
    Convert a Listing object with deal score into a dictionary format for API response.
    
    Args:
        listing: Facebook Marketplace listing
        deal_score: Calculated deal score percentage
        
    Returns:
        Dictionary containing listing data with deal score
    """
    return {
        "title": listing.title,
        "price": listing.price,
        "location": listing.location,
        "url": listing.url,
        "dealScore": deal_score,
    }


def filter_and_score_listings(
    fb_listings: List[Listing],
    ebay_stats: Optional[PriceStats],
    threshold: float
) -> List[dict]:
    """
    Filter listings by threshold as percentage of eBay average price and return scored results.
    
    Filters Facebook Marketplace listings to only include those priced at or below the
    threshold percentage of eBay average price. For example, a threshold of 80% means
    only listings priced at 80% of eBay average or less will be included. Each filtered
    listing is then scored to show percentage savings compared to eBay average.
    
    The function handles the case where eBay stats are unavailable by returning an
    empty list, ensuring robust behavior when external data is missing.
    
    Args:
        fb_listings: List of Facebook Marketplace listings to filter and score
        ebay_stats: eBay price statistics containing average price for comparison
        threshold: Maximum percentage of eBay average price to include (0-100).
                   For example, 80.0 means only listings at 80% of eBay price or less.
        
    Returns:
        List of dictionaries containing filtered listings with their deal scores.
        Each dictionary includes title, price, location, url, and dealScore fields.
        Returns empty list if eBay stats are unavailable or invalid.
    """
    if not ebay_stats or ebay_stats.average == 0:
        return []
    
    max_price = _calculate_max_price_for_threshold(ebay_stats.average, threshold)
    scored_listings = []
    
    for listing in fb_listings:
        if not _listing_meets_price_threshold(listing, max_price):
            continue
        
        deal_score = calculate_deal_score(listing.price, ebay_stats)
        if deal_score is None:
            continue
        
        scored_listings.append(_convert_listing_to_scored_dict(listing, deal_score))
    
    return scored_listings

