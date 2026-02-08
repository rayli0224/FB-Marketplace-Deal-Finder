"""
Listing processor for evaluating individual Facebook Marketplace listings.

Processes a single FB listing by generating an optimized eBay search query,
fetching comparable prices from eBay, and calculating a deal score. Returns
the listing with deal score if it meets the threshold, or None if it doesn't.
"""

import logging
from typing import Optional, Dict

from src.scrapers.fb_marketplace_scraper import Listing
from src.scrapers.ebay_scraper import get_market_price
from src.api.deal_calculator import calculate_deal_score
from src.utils.query_enhancer import generate_ebay_query_for_listing
from src.utils.colored_logger import setup_colored_logger

# Configure colored logging with module prefix
logger = setup_colored_logger("listing_processor")


def process_single_listing(
    listing: Listing,
    original_query: str,
    threshold: float = 20.0,
    n_items: int = 50,
    listing_index: Optional[int] = None,
    total_listings: Optional[int] = None
) -> Optional[Dict]:
    """
    Process a single FB listing to determine if it's a good deal.
    
    Orchestrates the full evaluation process:
    1. Generates an optimized eBay search query using OpenAI
    2. Fetches comparable prices from eBay using the generated query
    3. Calculates deal score (percentage savings vs eBay average)
    4. Returns listing dict with dealScore if it meets threshold, None otherwise
    
    If any step fails, returns None and logs the error. This ensures robust error
    handling without breaking the entire search process.
    
    Args:
        listing: Facebook Marketplace listing to evaluate
        original_query: The original user search query (e.g., "nintendo ds")
        threshold: Minimum deal score percentage to include (default: 20.0)
        n_items: Number of eBay listings to analyze for price comparison (default: 50)
        listing_index: Optional index of this listing (for progress tracking)
        total_listings: Optional total number of listings (for progress tracking)
        
    Returns:
        Dictionary with listing data and dealScore if meets threshold, None otherwise.
        Format: {
            "title": str,
            "price": float,
            "location": str,
            "url": str,
            "dealScore": float
        }
        
    Example:
        >>> listing = Listing(
        ...     title="Nintendo DS Lite Pink - Great Condition",
        ...     price=50.0,
        ...     location="New York, NY",
        ...     url="https://facebook.com/..."
        ... )
        >>> result = process_single_listing(listing, "nintendo ds", threshold=20.0)
        >>> if result:
        ...     print(f"Deal score: {result['dealScore']}%")
        ... else:
        ...     print("Listing doesn't meet threshold or processing failed")
    """
    progress_info = ""
    if listing_index is not None and total_listings is not None:
        progress_info = f"[{listing_index}/{total_listings}] "
    
    logger.info("")
    logger.info("=" * 80)
    logger.info(f"{progress_info}📋 FB Listing: '{listing.title}'")
    logger.info(f"   💰 Price: ${listing.price:.2f} | 📍 Location: {listing.location}")
    logger.info("=" * 80)
    
    logger.info("🔍 Step 1: Generating eBay search query with OpenAI...")
    query_result = generate_ebay_query_for_listing(listing, original_query)
    if not query_result:
        logger.warning(f"❌ Failed to generate eBay query - skipping listing")
        logger.info("")
        return None
    
    enhanced_query, exclusion_keywords = query_result
    
    logger.info(f"🔍 Step 2: Fetching eBay price data for query: '{enhanced_query}'...")
    ebay_stats = get_market_price(
        search_term=enhanced_query,
        n_items=n_items,
        excluded_keywords=exclusion_keywords,
    )
    
    if not ebay_stats:
        logger.warning(f"❌ No eBay stats found (insufficient data) - skipping listing")
        logger.info("")
        return None
    
    logger.info(f"   ✓ Found {ebay_stats.sample_size} eBay listings | Avg price: ${ebay_stats.average:.2f}")
    
    logger.info("🔍 Step 3: Calculating deal score...")
    deal_score = calculate_deal_score(listing.price, ebay_stats)
    
    if deal_score is None:
        logger.warning(f"❌ Could not calculate deal score - skipping listing")
        logger.info("")
        return None
    
    logger.info(f"   ✓ Deal score: {deal_score:.1f}% savings vs eBay average")
    
    # Check if meets threshold
    if deal_score < threshold:
        logger.info(f"⏭️  Deal score {deal_score:.1f}% below threshold {threshold}% - skipping")
        logger.info("")
        return None
    
    logger.info(f"✅ DEAL FOUND! {deal_score:.1f}% savings (FB: ${listing.price:.2f} vs eBay avg: ${ebay_stats.average:.2f})")
    logger.info("")
    
    # Return listing dict with deal score
    return {
        "title": listing.title,
        "price": listing.price,
        "location": listing.location,
        "url": listing.url,
        "dealScore": deal_score,
    }
