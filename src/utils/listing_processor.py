"""
Listing processor for evaluating individual Facebook Marketplace listings.

Processes a single FB listing by generating an optimized eBay search query,
fetching comparable prices from eBay, and calculating a deal score. Returns the
listing with deal score (or None when eBay data or calculation fails). All
listings are returned regardless of threshold or eBay data availability.
"""

import time
import logging
from typing import Dict, Optional

from src.scrapers.fb_marketplace_scraper import Listing
from src.scrapers.ebay_scraper import get_market_price
from src.api.deal_calculator import calculate_deal_score
from src.utils.query_enhancer import generate_ebay_query_for_listing
from src.utils.colored_logger import setup_colored_logger

# Configure colored logging with module prefix
logger = setup_colored_logger("listing_processor", level=logging.INFO)


def _listing_result(
    listing: Listing,
    deal_score: Optional[float],
    ebay_search_query: Optional[str] = None,
    comp_price: Optional[float] = None,
    comp_prices: Optional[list] = None,
    comp_items: Optional[list] = None,
) -> Dict:
    """
    Build the result dict for a processed listing.

    Always includes title, price, location, url, and dealScore. Adds
    ebaySearchQuery, compPrice, compPrices, and compItems only when the
    corresponding arguments are not None, so the API can omit transparency
    fields when eBay data was unavailable.
    """
    out = {
        "title": listing.title,
        "price": listing.price,
        "location": listing.location,
        "url": listing.url,
        "dealScore": deal_score,
    }
    if ebay_search_query is not None:
        out["ebaySearchQuery"] = ebay_search_query
    if comp_price is not None:
        out["compPrice"] = comp_price
    if comp_prices is not None:
        out["compPrices"] = comp_prices
    if comp_items is not None:
        out["compItems"] = comp_items
    return out


def process_single_listing(
    listing: Listing,
    original_query: str,
    threshold: float = 20.0,
    n_items: int = 50,
    listing_index: Optional[int] = None,
    total_listings: Optional[int] = None
) -> Dict:
    """
    Process a single FB listing: generate eBay query via OpenAI, fetch comparable
    prices, and calculate deal score (percentage savings vs eBay average).
    Returns listing dict with dealScore. When eBay stats are missing or calculation
    fails, dealScore is None so the UI shows "--".
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
        logger.warning(f"❌ Failed to generate eBay query - including listing with unknown deal score")
        logger.info("")
        return _listing_result(listing, None)

    enhanced_query, exclusion_keywords = query_result
    
    # Rate limiting delay for OpenAI API
    time.sleep(0.5)
    
    logger.info(f"🔍 Step 2: Fetching eBay price data for query: '{enhanced_query}'...")
    ebay_stats = get_market_price(
        search_term=enhanced_query,
        n_items=n_items,
        excluded_keywords=exclusion_keywords,
    )
    
    if not ebay_stats:
        logger.warning(f"❌ No eBay stats found (insufficient data) - including listing with unknown deal score")
        logger.info("")
        return _listing_result(listing, None)

    logger.info(f"   ✓ Found {ebay_stats.sample_size} eBay listings | Avg price: ${ebay_stats.average:.2f}")
    
    # Rate limiting delay for eBay API
    time.sleep(0.3)
    
    logger.info("🔍 Step 3: Calculating deal score...")
    deal_score = calculate_deal_score(listing.price, ebay_stats)
    
    if deal_score is None:
        logger.warning(f"❌ Could not calculate deal score - including listing with unknown deal score")
        logger.info("")
        return _listing_result(listing, None)

    logger.info(f"   ✓ Deal score: {deal_score:.1f}% savings vs eBay average")
    if deal_score >= threshold:
        logger.info(f"✅ DEAL FOUND! {deal_score:.1f}% savings (FB: ${listing.price:.2f} vs eBay avg: ${ebay_stats.average:.2f})")
    else:
        logger.info(f"⏭️  Deal score {deal_score:.1f}% below threshold {threshold}% - including anyway")
    logger.info("")

    return _listing_result(
        listing,
        deal_score,
        ebay_search_query=enhanced_query,
        comp_price=ebay_stats.average,
        comp_prices=ebay_stats.raw_prices,
        comp_items=getattr(ebay_stats, "item_summaries", None),
    )
